"""
Discord service for posting daily digests via webhooks.

Uses Discord webhooks for simple posting without requiring a bot process.
"""

from datetime import date

import httpx

from app.config import get_config, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Topic colors for visual variety in embeds
TOPIC_COLORS = {
    "default": 0x5865F2,  # Discord blurple
    "release": 0x2ECC71,  # Green - releases/changelogs
    "security": 0xE74C3C,  # Red - security/CVE
    "ai": 0x9B59B6,  # Purple - AI/ML
    "infrastructure": 0x3498DB,  # Blue - cloud/infra
    "viral": 0xE91E63,  # Pink - viral/trending
}


def _get_embed_color(item: dict) -> int:
    """Determine embed color based on content keywords."""
    headline = (item.get("headline") or "").lower()
    teaser = (item.get("teaser") or "").lower()
    content = f"{headline} {teaser}"

    if any(kw in content for kw in ["release", "changelog", "v1.", "v2.", "launched"]):
        return TOPIC_COLORS["release"]
    if any(kw in content for kw in ["cve", "security", "vulnerability", "exploit", "patch"]):
        return TOPIC_COLORS["security"]
    if any(kw in content for kw in ["ai", "llm", "gpt", "claude", "model", "training"]):
        return TOPIC_COLORS["ai"]
    if any(kw in content for kw in ["kubernetes", "docker", "aws", "gcp", "azure", "cloud"]):
        return TOPIC_COLORS["infrastructure"]

    return TOPIC_COLORS["default"]


def build_digest_embeds(issue_date: date, items: list[dict]) -> list[dict]:
    """
    Build Discord embeds for the daily digest.

    Args:
        issue_date: Date of the issue
        items: List of issue items with summaries

    Returns:
        List of Discord embed dictionaries
    """
    settings = get_settings()
    embeds = []

    # Header embed
    embeds.append(
        {
            "title": f"Noyau - {issue_date}",
            "description": "10 things worth knowing in tech today",
            "color": 0x000000,
            "url": f"{settings.base_url}/daily/{issue_date}",
            "footer": {"text": "noyau.news"},
        }
    )

    # Item embeds
    for idx, item in enumerate(items, start=1):
        embed = {
            "title": f"#{idx}  {item.get('headline', 'Untitled')}",
            "description": item.get("teaser", ""),
            "color": _get_embed_color(item),
            "fields": [],
        }

        # Add takeaway if present
        takeaway = item.get("takeaway")
        if takeaway:
            embed["fields"].append(
                {
                    "name": "Takeaway",
                    "value": takeaway[:1024],
                    "inline": False,
                }
            )

        # Add bullets if present
        bullets = item.get("bullets")
        if bullets and isinstance(bullets, list):
            bullets_text = "\n".join([f"• {b}" for b in bullets[:5]])
            if bullets_text:
                embed["fields"].append(
                    {
                        "name": "Key Points",
                        "value": bullets_text[:1024],
                        "inline": False,
                    }
                )

        # Add sources/citations
        citations = item.get("citations")
        if citations and isinstance(citations, list):
            sources = []
            for c in citations[:3]:
                if isinstance(c, dict):
                    label = c.get("label", "Source")
                    url = c.get("url", "")
                    if url:
                        sources.append(f"[{label}]({url})")
            if sources:
                embed["fields"].append(
                    {
                        "name": "Sources",
                        "value": "\n".join(sources),
                        "inline": False,
                    }
                )

        embeds.append(embed)

    return embeds


async def send_discord_digest(issue_date: date, items: list[dict]) -> bool:
    """
    Send daily digest to Discord via webhook.

    Args:
        issue_date: Date of the issue
        items: List of issue items with summaries

    Returns:
        True if successful, False otherwise
    """
    config = get_config()

    # Check if Discord is enabled
    if not config.discord.enabled:
        logger.debug("discord_disabled")
        return False

    webhook_url = config.discord.webhook_url
    if not webhook_url:
        logger.warning("discord_webhook_url_not_set")
        return False

    embeds = build_digest_embeds(issue_date, items)

    # Discord webhooks allow max 10 embeds per message
    # Send header + first 9 items in first batch, then remaining item(s)
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # First batch (header + items 1-9)
            first_batch = embeds[:10]
            payload = {"embeds": first_batch}

            resp = await client.post(webhook_url, json=payload)

            if resp.status_code not in (200, 204):
                logger.bind(
                    status=resp.status_code,
                    body=resp.text[:500],
                ).error("discord_webhook_failed")
                return False

            # Second batch (item 10+ if present)
            if len(embeds) > 10:
                second_batch = embeds[10:]
                payload = {"embeds": second_batch}

                resp = await client.post(webhook_url, json=payload)

                if resp.status_code not in (200, 204):
                    logger.bind(
                        status=resp.status_code,
                        body=resp.text[:500],
                    ).error("discord_webhook_failed_batch2")
                    return False

            logger.bind(date=str(issue_date), items=len(items)).info("discord_digest_sent")
            return True

        except httpx.TimeoutException:
            logger.error("discord_webhook_timeout")
            return False
        except Exception as e:
            logger.bind(error=str(e)).error("discord_send_error")
            return False


async def send_discord_subscription_notification(
    email: str,
    timezone: str | None = None,
    delivery_time: str | None = None,
) -> bool:
    """
    Send notification to Discord when a new user subscribes via email.

    Args:
        email: New subscriber's email
        timezone: User's timezone preference
        delivery_time: User's preferred delivery time

    Returns:
        True if successful, False otherwise
    """
    config = get_config()

    webhook_url = config.discord.webhook_url
    if not webhook_url:
        logger.debug("discord_webhook_url_not_set")
        return False

    # Build fields
    fields: list[dict[str, str | bool]] = [
        {"name": "Email", "value": email, "inline": True},
    ]
    if timezone:
        fields.append({"name": "Timezone", "value": timezone, "inline": True})
    if delivery_time:
        fields.append({"name": "Delivery Time", "value": delivery_time, "inline": True})

    embed = {
        "title": "New Email Subscriber",
        "description": "A new user just subscribed to the daily digest!",
        "color": 0x2ECC71,  # Green
        "fields": fields,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(webhook_url, json={"embeds": [embed]})

            if resp.status_code not in (200, 204):
                logger.bind(status=resp.status_code).error("discord_subscription_webhook_failed")
                return False

            logger.bind(email=email).debug("discord_subscription_notification_sent")
            return True

        except httpx.TimeoutException:
            logger.error("discord_subscription_webhook_timeout")
            return False
        except Exception as e:
            logger.bind(error=str(e)).error("discord_subscription_notification_failed")
            return False


async def send_discord_error(
    title: str,
    error: str,
    context: dict | None = None,
) -> bool:
    """
    Send error notification to Discord via error webhook.

    Args:
        title: Error title/summary
        error: Error message/details
        context: Optional context dict (email, endpoint, etc.)

    Returns:
        True if successful, False otherwise
    """
    config = get_config()

    error_webhook_url = config.discord.error_webhook_url
    if not error_webhook_url:
        logger.debug("discord_error_webhook_not_set")
        return False

    # Build fields from context
    fields: list[dict[str, str | bool]] = []
    if context:
        for key, value in context.items():
            fields.append(
                {
                    "name": key,
                    "value": str(value)[:1024],
                    "inline": True,
                }
            )

    # Build embed
    embed = {
        "title": f":warning: {title}",
        "description": error[:2000],
        "color": 0xE74C3C,  # Red
        "fields": fields,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(error_webhook_url, json={"embeds": [embed]})

            if resp.status_code not in (200, 204):
                logger.bind(status=resp.status_code).error("discord_error_webhook_failed")
                return False

            logger.debug("discord_error_sent")
            return True

        except httpx.TimeoutException:
            logger.error("discord_error_webhook_timeout")
            return False
        except Exception as e:
            logger.bind(error=str(e)).error("discord_error_send_failed")
            return False
