"""
Discord DM service for sending daily digests to subscribed users.

Used by the daily job to send digest DMs to all active Discord subscribers.
Does not require a running bot process - uses Discord's REST API directly.
"""

from dataclasses import dataclass
from datetime import date

import httpx
from sqlalchemy import select

from app.config import get_config
from app.core.database import AsyncSessionLocal
from app.core.datetime_utils import utc_now
from app.core.logging import get_logger
from app.models.messaging import MessagingConnection

logger = get_logger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"


@dataclass
class DiscordDMResult:
    """Result of sending Discord DMs."""

    sent: int
    failed: int
    success: bool
    message: str


def build_dm_embeds(issue_date: date, items: list[dict], base_url: str) -> list[dict]:
    """
    Build Discord embeds for DM digest.

    Simplified format compared to channel posts - fewer embeds, more compact.
    """
    embeds = []

    # Header embed with all items in description
    description_lines = []
    for idx, item in enumerate(items, start=1):
        headline = item.get("headline", "Untitled")
        teaser = item.get("teaser", "")
        # Truncate teaser for compact view
        if len(teaser) > 100:
            teaser = teaser[:97] + "..."
        description_lines.append(f"**{idx}. {headline}**\n{teaser}")

    description = "\n\n".join(description_lines[:5])  # First 5 items in first embed

    embeds.append(
        {
            "title": f"Noyau Daily - {issue_date}",
            "description": description,
            "color": 0x000000,
            "url": f"{base_url}/daily/{issue_date}",
        }
    )

    # Second embed for items 6-10
    if len(items) > 5:
        description_lines_2 = []
        for idx, item in enumerate(items[5:], start=6):
            headline = item.get("headline", "Untitled")
            teaser = item.get("teaser", "")
            if len(teaser) > 100:
                teaser = teaser[:97] + "..."
            description_lines_2.append(f"**{idx}. {headline}**\n{teaser}")

        embeds.append(
            {
                "description": "\n\n".join(description_lines_2),
                "color": 0x000000,
            }
        )

    # Footer embed with CTA
    embeds.append(
        {
            "description": f"[Read full digest on noyau.news]({base_url}/daily/{issue_date})\n\n"
            f"Reply `/unsubscribe` in any server with the bot to stop receiving these DMs.",
            "color": 0x5865F2,  # Discord blurple
        }
    )

    return embeds


async def open_dm_channel(
    client: httpx.AsyncClient,
    bot_token: str,
    user_id: str,
) -> str | None:
    """Open a DM channel with a user."""
    try:
        resp = await client.post(
            f"{DISCORD_API_BASE}/users/@me/channels",
            headers={"Authorization": f"Bot {bot_token}"},
            json={"recipient_id": user_id},
        )

        if resp.status_code == 200:
            channel_id = resp.json().get("id")
            return str(channel_id) if channel_id else None

        logger.bind(
            status=resp.status_code,
            user_id=user_id,
        ).warning("discord_dm_channel_open_failed")
        return None

    except Exception as e:
        logger.bind(error=str(e), user_id=user_id).error("discord_dm_channel_error")
        return None


async def send_dm_message(
    client: httpx.AsyncClient,
    bot_token: str,
    channel_id: str,
    embeds: list[dict],
) -> bool:
    """Send a message to a DM channel."""
    try:
        resp = await client.post(
            f"{DISCORD_API_BASE}/channels/{channel_id}/messages",
            headers={"Authorization": f"Bot {bot_token}"},
            json={"embeds": embeds},
        )

        if resp.status_code in (200, 201):
            return True

        logger.bind(
            status=resp.status_code,
            channel_id=channel_id,
        ).warning("discord_dm_send_failed")
        return False

    except Exception as e:
        logger.bind(error=str(e), channel_id=channel_id).error("discord_dm_error")
        return False


async def send_discord_digests(issue_date: date, items: list[dict]) -> DiscordDMResult:
    """
    Send daily digest DMs to all active Discord subscribers.

    Args:
        issue_date: Date of the issue
        items: List of issue items with summaries

    Returns:
        DiscordDMResult with sent/failed counts
    """
    config = get_config()

    if not config.discord_bot.enabled:
        logger.debug("discord_bot_disabled")
        return DiscordDMResult(sent=0, failed=0, success=True, message="Discord bot disabled")

    bot_token = config.discord_bot.bot_token
    if not bot_token:
        logger.warning("discord_bot_token_not_set")
        return DiscordDMResult(sent=0, failed=0, success=False, message="Bot token not set")

    base_url = config.settings.base_url
    embeds = build_dm_embeds(issue_date, items, base_url)

    sent_count = 0
    failed_count = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        async with AsyncSessionLocal() as db:
            # Get all active Discord connections
            result = await db.execute(
                select(MessagingConnection).where(
                    MessagingConnection.platform == "discord",
                    MessagingConnection.is_active.is_(True),
                )
            )
            connections = result.scalars().all()

            if not connections:
                logger.debug("no_active_discord_subscribers")
                return DiscordDMResult(
                    sent=0, failed=0, success=True, message="No active subscribers"
                )

            for connection in connections:
                try:
                    # Open DM channel
                    channel_id = await open_dm_channel(
                        client, bot_token, connection.platform_user_id
                    )

                    if not channel_id:
                        failed_count += 1
                        continue

                    # Send message
                    success = await send_dm_message(client, bot_token, channel_id, embeds)

                    if success:
                        connection.last_sent_at = utc_now()
                        sent_count += 1
                    else:
                        failed_count += 1

                except Exception as e:
                    logger.bind(
                        user_id=connection.platform_user_id,
                        error=str(e),
                    ).error("discord_dm_dispatch_error")
                    failed_count += 1

            await db.commit()

    message = f"Sent {sent_count} DMs"
    if failed_count > 0:
        message += f", {failed_count} failed"

    logger.bind(sent=sent_count, failed=failed_count).info("discord_dm_dispatch_completed")

    return DiscordDMResult(
        sent=sent_count,
        failed=failed_count,
        success=sent_count > 0 or failed_count == 0,
        message=message,
    )
