from pathlib import Path

import resend
from jinja2 import Environment, FileSystemLoader

from app.config import get_config, get_settings
from app.core.logging import get_logger
from app.core.security import build_magic_link_url, generate_unsubscribe_token

logger = get_logger(__name__)

# Initialize Jinja2 environment for email templates
template_dir = Path(__file__).parent.parent / "emails" / "templates"
jinja_env = Environment(loader=FileSystemLoader(template_dir), autoescape=True)


def _init_resend() -> None:
    """Initialize Resend API with API key."""
    settings = get_settings()
    if settings.resend_api_key:
        resend.api_key = settings.resend_api_key


async def send_magic_link_email(
    email: str,
    token: str,
    redirect_path: str = "/",
    timezone: str | None = None,
    delivery_time_local: str | None = None,
) -> None:
    """
    Send a magic link email to the user.

    Args:
        email: Recipient email address
        token: The raw (unhashed) magic link token
        redirect_path: Path to redirect to after login
        timezone: Optional IANA timezone for new users
        delivery_time_local: Optional delivery time in HH:MM format
    """
    _init_resend()
    settings = get_settings()

    magic_url = build_magic_link_url(
        token,
        redirect_path,
        timezone=timezone,
        delivery_time_local=delivery_time_local,
    )

    try:
        template = jinja_env.get_template("magic_link.html")
        html = template.render(
            magic_url=magic_url,
            redirect_path=redirect_path,
        )
    except Exception:
        # Fallback to simple HTML if template not found
        html = f"""
        <html>
        <body style="font-family: sans-serif; padding: 20px;">
            <h2>Sign in to NoyauAI</h2>
            <p>Click the button below to sign in to your account:</p>
            <p>
                <a href="{magic_url}"
                   style="background-color: #000; color: #fff; padding: 12px 24px;
                          text-decoration: none; border-radius: 4px; display: inline-block;">
                    Sign In
                </a>
            </p>
            <p style="color: #666; font-size: 14px;">
                This link expires in 15 minutes.
            </p>
            <p style="color: #999; font-size: 12px;">
                If you didn't request this link, you can safely ignore this email.
            </p>
        </body>
        </html>
        """

    logger.bind(email=email).info("sending_magic_link")

    if not settings.resend_api_key:
        logger.bind(email=email, magic_url=magic_url).warning("resend_api_key_not_set")
        return

    resend.Emails.send(
        {
            "from": f"NoyauNews <noreply@{settings.email_domain}>",
            "to": [email],
            "subject": "Sign in to NoyauNews",
            "html": html,
        }
    )

    logger.bind(email=email).info("magic_link_sent")


async def send_daily_digest(
    email: str,
    issue_date: str,
    items: list[dict],
    missed_items: list[dict] | None = None,
) -> None:
    """
    Send the daily digest email.

    Args:
        email: Recipient email address
        issue_date: Date of the issue (YYYY-MM-DD)
        items: List of issue items with summaries
        missed_items: Optional list of items from yesterday for "You may have missed"
    """
    _init_resend()
    settings = get_settings()
    config = get_config()

    issue_url = f"{settings.base_url}/daily/{issue_date}"
    discord_invite_url = config.discord.invite_url if config.discord.enabled else ""

    # Generate unsubscribe URL with HMAC token
    unsubscribe_token = generate_unsubscribe_token(email)
    unsubscribe_url = (
        f"{settings.base_url}/auth/unsubscribe?email={email}&token={unsubscribe_token}"
    )

    try:
        template = jinja_env.get_template("daily_digest.html")
        html = template.render(
            issue_date=issue_date,
            full_items=items[:5],
            teaser_items=items[5:10],
            missed_items=missed_items or [],
            issue_url=issue_url,
            discord_invite_url=discord_invite_url,
            unsubscribe_url=unsubscribe_url,
        )
    except Exception as e:
        logger.bind(error=str(e)).error("template_error")
        return

    logger.bind(email=email, issue_date=issue_date).info("sending_daily_digest")

    if not settings.resend_api_key:
        logger.bind(email=email).warning("resend_api_key_not_set")
        return

    # A/B subject lines (simple alternation based on email hash)
    if hash(email) % 2 == 0:
        subject = f"Noyau - {issue_date} (10 things worth knowing)"
    else:
        subject = "10 things worth knowing today - Noyau"

    resend.Emails.send(
        {
            "from": f"NoyauNews <digest@{settings.email_domain}>",
            "to": [email],
            "subject": subject,
            "html": html,
        }
    )

    logger.bind(email=email, issue_date=issue_date).info("daily_digest_sent")


async def send_test_emails() -> dict[str, bool | str]:
    """
    Send test emails (magic link + daily digest) to the configured DEV_EMAIL.

    Returns:
        Dict with success status for each email type
    """
    settings = get_settings()

    if not settings.dev_email:
        logger.warning("dev_email_not_configured")
        return {"magic_link": False, "daily_digest": False, "error": "DEV_EMAIL not set"}

    if not settings.resend_api_key:
        logger.warning("resend_api_key_not_set")
        return {"magic_link": False, "daily_digest": False, "error": "RESEND_API_KEY not set"}

    results: dict[str, bool | str] = {"magic_link": False, "daily_digest": False}

    # Test magic link email
    try:
        await send_magic_link_email(
            email=settings.dev_email,
            token="test-token-12345",
            redirect_path="/",
        )
        results["magic_link"] = True
        logger.bind(email=settings.dev_email).info("test_magic_link_sent")
    except Exception as e:
        logger.bind(error=str(e)).error("test_magic_link_failed")

    # Test daily digest email with sample data
    try:
        sample_items = [
            {
                "headline": "OpenAI releases GPT-5 with unprecedented reasoning",
                "teaser": "The new model shows 40% improvement on complex math benchmarks and introduces native multi-modal understanding.",
                "bullets": [
                    "Context window expanded to 1M tokens",
                    "Native code execution in sandbox",
                    "Available via API today",
                ],
                "citations": [
                    {"url": "https://openai.com/blog", "label": "OpenAI Blog"},
                    {"url": "https://news.ycombinator.com", "label": "HN Discussion"},
                ],
            },
            {
                "headline": "Rust 2.0 brings async/await improvements",
                "teaser": "Major release focuses on ergonomics and compile times with backward compatibility.",
                "bullets": ["50% faster compile times", "Simplified lifetime syntax"],
                "citations": [{"url": "https://rust-lang.org", "label": "Rust Blog"}],
            },
            {
                "headline": "GitHub Copilot now suggests entire features",
                "teaser": "New 'Workspace' mode analyzes your codebase to suggest complete implementations.",
                "citations": [{"url": "https://github.blog", "label": "GitHub Blog"}],
            },
            {
                "headline": "PostgreSQL 17 improves JSON performance 10x",
                "teaser": "New binary JSON format and optimized operators make Postgres competitive with document DBs.",
                "citations": [{"url": "https://postgresql.org", "label": "PG Release"}],
            },
            {
                "headline": "Kubernetes 1.32 simplifies networking",
                "teaser": "Gateway API becomes default, CNI plugins now optional for simple deployments.",
                "citations": [{"url": "https://kubernetes.io", "label": "K8s Blog"}],
            },
            {
                "headline": "AWS announces 50% price cut on Lambda",
                "teaser": "Aggressive pricing move targets serverless market share.",
                "citations": [{"url": "https://aws.amazon.com/blogs", "label": "AWS Blog"}],
            },
            {
                "headline": "SQLite adds vector search extension",
                "teaser": "Embedded databases can now run similarity searches locally.",
                "citations": [{"url": "https://sqlite.org/changes", "label": "SQLite"}],
            },
            {
                "headline": "Deno 3.0 achieves Node.js parity",
                "teaser": "Full npm compatibility and improved performance benchmarks.",
                "citations": [{"url": "https://deno.com/blog", "label": "Deno Blog"}],
            },
            {
                "headline": "Linux kernel 6.12 brings real-time by default",
                "teaser": "PREEMPT_RT merged into mainline after 20 years of development.",
                "citations": [{"url": "https://lwn.net", "label": "LWN"}],
            },
            {
                "headline": "Apple open-sources MLX 2.0",
                "teaser": "Machine learning framework optimized for Apple Silicon reaches feature parity.",
                "citations": [{"url": "https://github.com/ml-explore/mlx", "label": "GitHub"}],
            },
        ]

        from datetime import date

        test_date = date.today().isoformat()

        await send_daily_digest(
            email=settings.dev_email,
            issue_date=test_date,
            items=sample_items,
        )
        results["daily_digest"] = True
        logger.bind(email=settings.dev_email).info("test_daily_digest_sent")
    except Exception as e:
        logger.bind(error=str(e)).error("test_daily_digest_failed")

    return results
