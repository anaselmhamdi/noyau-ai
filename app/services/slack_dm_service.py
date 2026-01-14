"""
Slack DM service for sending daily digest to subscribers.

Called by the daily job to send digest DMs to all Slack subscribers.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select

from app.config import get_config
from app.core.database import AsyncSessionLocal
from app.core.datetime_utils import utc_now
from app.core.logging import get_logger
from app.models.messaging import MessagingConnection
from app.services.slack_service import build_digest_blocks, send_dm

logger = get_logger(__name__)


@dataclass
class SlackDispatchResult:
    """Result of sending Slack digests."""

    success: bool
    sent: int
    failed: int
    message: str


async def send_slack_digests(issue_date: date, items: list[dict]) -> SlackDispatchResult:
    """
    Send daily digest to all Slack subscribers.

    Args:
        issue_date: Date of the issue
        items: List of issue items

    Returns:
        SlackDispatchResult with counts
    """
    config = get_config()

    if not config.slack.enabled:
        logger.debug("slack_disabled")
        return SlackDispatchResult(
            success=True,
            sent=0,
            failed=0,
            message="Slack disabled",
        )

    blocks = build_digest_blocks(issue_date, items)

    sent_count = 0
    failed_count = 0

    async with AsyncSessionLocal() as db:
        # Get all active Slack connections
        query_result = await db.execute(
            select(MessagingConnection).where(
                MessagingConnection.platform == "slack",
                MessagingConnection.is_active.is_(True),
            )
        )
        connections = query_result.scalars().all()

        if not connections:
            logger.debug("no_slack_subscribers")
            return SlackDispatchResult(
                success=True,
                sent=0,
                failed=0,
                message="No Slack subscribers",
            )

        for connection in connections:
            if not connection.access_token:
                logger.bind(user_id=str(connection.user_id)).warning(
                    "slack_connection_missing_token"
                )
                failed_count += 1
                continue

            try:
                result = await send_dm(
                    access_token=connection.access_token,
                    user_id=connection.platform_user_id,
                    blocks=blocks,
                    text=f"Noyau Daily - {issue_date}",
                )

                if result.success:
                    connection.last_sent_at = utc_now()
                    sent_count += 1
                    logger.bind(
                        slack_user_id=connection.platform_user_id,
                        team_id=connection.platform_team_id,
                    ).debug("slack_dm_sent")
                else:
                    logger.bind(
                        slack_user_id=connection.platform_user_id,
                        error=result.error,
                    ).warning("slack_dm_failed")

                    # Deactivate if token revoked
                    if result.error in ["token_revoked", "account_inactive", "invalid_auth"]:
                        connection.is_active = False

                    failed_count += 1

            except Exception as e:
                logger.bind(
                    slack_user_id=connection.platform_user_id,
                    error=str(e),
                ).error("slack_dm_error")
                failed_count += 1

        await db.commit()

    return SlackDispatchResult(
        success=sent_count > 0 or failed_count == 0,
        sent=sent_count,
        failed=failed_count,
        message=f"Sent {sent_count}, failed {failed_count}",
    )
