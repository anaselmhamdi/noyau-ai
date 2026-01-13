"""
Slack service for OAuth and sending daily digest DMs.

Users install the Slack app via OAuth and receive daily digest DMs.
"""

from dataclasses import dataclass
from datetime import date
from urllib.parse import urlencode

import httpx

from app.config import get_config, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Slack API endpoints
SLACK_OAUTH_URL = "https://slack.com/api/oauth.v2.access"
SLACK_USER_INFO_URL = "https://slack.com/api/users.info"
SLACK_CONVERSATIONS_OPEN_URL = "https://slack.com/api/conversations.open"
SLACK_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"


@dataclass
class SlackOAuthResult:
    """Result of Slack OAuth flow."""

    access_token: str
    team_id: str
    team_name: str
    authed_user_id: str
    authed_user_email: str | None = None


@dataclass
class SlackSendResult:
    """Result of sending a Slack message."""

    success: bool
    channel: str | None = None
    ts: str | None = None
    error: str | None = None


def build_oauth_url(redirect_uri: str, state: str | None = None) -> str:
    """
    Build Slack OAuth authorization URL.

    Args:
        redirect_uri: OAuth callback URL
        state: Optional CSRF state parameter

    Returns:
        Authorization URL
    """
    config = get_config()

    params = {
        "client_id": config.slack.client_id,
        "scope": ",".join(config.slack.scopes),
        "user_scope": "openid,email",
        "redirect_uri": redirect_uri,
    }

    if state:
        params["state"] = state

    return f"https://slack.com/oauth/v2/authorize?{urlencode(params)}"


async def exchange_code_for_tokens(
    code: str,
    redirect_uri: str,
) -> SlackOAuthResult | None:
    """
    Exchange OAuth authorization code for access token.

    Args:
        code: Authorization code from OAuth callback
        redirect_uri: Must match the redirect_uri used in authorize

    Returns:
        SlackOAuthResult if successful
    """
    config = get_config()

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                SLACK_OAUTH_URL,
                data={
                    "client_id": config.slack.client_id,
                    "client_secret": config.slack.client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            )

            data = resp.json()

            if not data.get("ok"):
                logger.bind(error=data.get("error")).error("slack_oauth_failed")
                return None

            # Get user email from authed_user if available
            authed_user = data.get("authed_user", {})
            email = authed_user.get("email")

            return SlackOAuthResult(
                access_token=data["access_token"],
                team_id=data["team"]["id"],
                team_name=data["team"]["name"],
                authed_user_id=authed_user.get("id", ""),
                authed_user_email=email,
            )

        except Exception as e:
            logger.bind(error=str(e)).error("slack_oauth_exchange_error")
            return None


async def get_user_email(access_token: str, user_id: str) -> str | None:
    """
    Get email for a Slack user.

    Args:
        access_token: Bot access token
        user_id: Slack user ID

    Returns:
        Email address if found
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                SLACK_USER_INFO_URL,
                params={"user": user_id},
                headers={"Authorization": f"Bearer {access_token}"},
            )

            data = resp.json()

            if data.get("ok"):
                email: str | None = data.get("user", {}).get("profile", {}).get("email")
                return email

            return None

        except Exception as e:
            logger.bind(error=str(e)).error("slack_get_user_email_error")
            return None


async def open_dm_channel(access_token: str, user_id: str) -> str | None:
    """
    Open a DM channel with a user.

    Args:
        access_token: Bot access token
        user_id: Slack user ID

    Returns:
        Channel ID if successful
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                SLACK_CONVERSATIONS_OPEN_URL,
                json={"users": user_id},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )

            data = resp.json()

            if data.get("ok"):
                channel_id: str | None = data.get("channel", {}).get("id")
                return channel_id

            logger.bind(error=data.get("error")).warning("slack_open_dm_failed")
            return None

        except Exception as e:
            logger.bind(error=str(e)).error("slack_open_dm_error")
            return None


async def send_dm(
    access_token: str,
    user_id: str,
    blocks: list[dict],
    text: str = "Daily Digest from Noyau",
) -> SlackSendResult:
    """
    Send a DM to a user using Block Kit.

    Args:
        access_token: Bot access token
        user_id: Slack user ID
        blocks: Block Kit blocks
        text: Fallback text for notifications

    Returns:
        SlackSendResult
    """
    # First open DM channel
    channel_id = await open_dm_channel(access_token, user_id)

    if not channel_id:
        return SlackSendResult(
            success=False,
            error="Could not open DM channel",
        )

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                SLACK_POST_MESSAGE_URL,
                json={
                    "channel": channel_id,
                    "blocks": blocks,
                    "text": text,
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )

            data = resp.json()

            if data.get("ok"):
                return SlackSendResult(
                    success=True,
                    channel=channel_id,
                    ts=data.get("ts"),
                )
            else:
                return SlackSendResult(
                    success=False,
                    error=data.get("error", "Unknown error"),
                )

        except Exception as e:
            return SlackSendResult(
                success=False,
                error=str(e),
            )


# Topic emoji mapping for Block Kit
TOPIC_EMOJI = {
    "default": ":newspaper:",
    "release": ":rocket:",
    "security": ":rotating_light:",
    "ai": ":robot_face:",
    "infrastructure": ":cloud:",
}


def _get_topic_emoji(item: dict) -> str:
    """Determine emoji based on content keywords."""
    headline = (item.get("headline") or "").lower()
    teaser = (item.get("teaser") or "").lower()
    content = f"{headline} {teaser}"

    if any(kw in content for kw in ["release", "changelog", "v1.", "v2.", "launched"]):
        return TOPIC_EMOJI["release"]
    if any(kw in content for kw in ["cve", "security", "vulnerability", "exploit"]):
        return TOPIC_EMOJI["security"]
    if any(kw in content for kw in ["ai", "llm", "gpt", "claude", "model"]):
        return TOPIC_EMOJI["ai"]
    if any(kw in content for kw in ["kubernetes", "docker", "aws", "cloud"]):
        return TOPIC_EMOJI["infrastructure"]

    return TOPIC_EMOJI["default"]


def build_digest_blocks(issue_date: date, items: list[dict]) -> list[dict]:
    """
    Build Slack Block Kit blocks for the daily digest.

    Args:
        issue_date: Date of the issue
        items: List of issue items (all 10)

    Returns:
        List of Block Kit block dicts
    """
    settings = get_settings()
    issue_url = f"{settings.base_url}/daily/{issue_date}"

    blocks: list[dict] = []

    # Header
    blocks.append(
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":zap: Noyau Daily - {issue_date}",
                "emoji": True,
            },
        }
    )

    blocks.append(
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "10 things worth knowing in tech today"}],
        }
    )

    blocks.append({"type": "divider"})

    # Items
    for idx, item in enumerate(items, start=1):
        emoji = _get_topic_emoji(item)
        headline = item.get("headline", "Untitled")
        teaser = item.get("teaser", "")

        # Main item
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{idx}. {emoji} {headline}*\n{teaser}"},
            }
        )

        # Bullets
        bullets = item.get("bullets")
        if bullets and isinstance(bullets, list):
            bullets_text = "\n".join([f"• {b}" for b in bullets[:3]])
            blocks.append(
                {"type": "context", "elements": [{"type": "mrkdwn", "text": bullets_text}]}
            )

        # Takeaway
        takeaway = item.get("takeaway")
        if takeaway:
            blocks.append(
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": f":bulb: _{takeaway}_"}],
                }
            )

        # Sources
        citations = item.get("citations")
        if citations and isinstance(citations, list):
            sources = []
            for c in citations[:2]:
                if isinstance(c, dict):
                    label = c.get("label", "Source")
                    url = c.get("url", "")
                    if url:
                        sources.append(f"<{url}|{label}>")
            if sources:
                blocks.append(
                    {
                        "type": "context",
                        "elements": [{"type": "mrkdwn", "text": ":link: " + " | ".join(sources)}],
                    }
                )

        # Divider between items
        if idx < len(items):
            blocks.append({"type": "divider"})

    # Footer
    blocks.append({"type": "divider"})

    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": ":globe_with_meridians: Read on web",
                        "emoji": True,
                    },
                    "url": issue_url,
                    "action_id": "read_on_web",
                }
            ],
        }
    )

    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"<{settings.base_url}|noyau.news> - More signal, less noise",
                }
            ],
        }
    )

    return blocks
