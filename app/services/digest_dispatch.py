"""Timezone-aware digest dispatch service.

Handles sending digests to users based on their local delivery time preferences.
"""

from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import (
    has_delivery_window_passed,
    is_in_delivery_window,
    utc_now,
)
from app.core.logging import get_logger
from app.models.cluster import Cluster, ClusterSummary
from app.models.digest_delivery import DigestDelivery
from app.models.user import User
from app.pipeline.issue_builder import get_missed_from_yesterday
from app.services.email_service import send_daily_digest

logger = get_logger(__name__)


async def get_users_ready_for_delivery(
    db: AsyncSession,
    issue_date: date,
) -> list[User]:
    """Get users who are ready to receive the digest.

    A user is ready if:
    1. They are subscribed (is_subscribed=True)
    2. They haven't received this issue yet (no DigestDelivery record)
    3. Their local time is within their delivery window OR the window has passed
       (catch-up logic for late subscribers)

    Args:
        db: Database session
        issue_date: The issue date to check delivery for

    Returns:
        List of users ready for digest delivery
    """
    # Get all subscribed users who haven't received this issue
    subquery = (
        select(DigestDelivery.user_id)
        .where(DigestDelivery.issue_date == issue_date)
        .scalar_subquery()
    )

    result = await db.execute(
        select(User).where(
            and_(
                User.is_subscribed == True,  # noqa: E712
                User.id.not_in(subquery),
            )
        )
    )
    users = result.scalars().all()

    # Filter to users whose delivery window is active or has passed
    ready_users = []
    for user in users:
        in_window = is_in_delivery_window(user.timezone, user.delivery_time_local)
        window_passed = has_delivery_window_passed(user.timezone, user.delivery_time_local)

        if in_window or window_passed:
            ready_users.append(user)
            logger.bind(
                user_id=str(user.id),
                email=user.email,
                timezone=user.timezone,
                delivery_time=user.delivery_time_local,
                in_window=in_window,
                window_passed=window_passed,
            ).debug("user_ready_for_delivery")

    return ready_users


async def record_delivery(
    db: AsyncSession,
    user: User,
    issue_date: date,
) -> DigestDelivery:
    """Record that a user has received the digest for a given date.

    Args:
        db: Database session
        user: The user who received the digest
        issue_date: The issue date delivered

    Returns:
        The created DigestDelivery record
    """
    delivery = DigestDelivery(
        user_id=user.id,
        issue_date=issue_date,
        delivered_at=utc_now(),
    )
    db.add(delivery)
    await db.flush()
    return delivery


async def get_issue_items_for_date(db: AsyncSession, issue_date: date) -> list[dict]:
    """Fetch issue items for the given date.

    Args:
        db: Database session
        issue_date: The issue date to fetch

    Returns:
        List of item dicts with headline, teaser, bullets, citations
    """
    clusters_result = await db.execute(
        select(Cluster)
        .where(Cluster.issue_date == issue_date)
        .order_by(Cluster.cluster_score.desc())
        .limit(10)
    )
    clusters = clusters_result.scalars().all()

    items = []
    for cluster in clusters:
        summary_result = await db.execute(
            select(ClusterSummary).where(ClusterSummary.cluster_id == cluster.id)
        )
        summary = summary_result.scalar_one_or_none()

        if summary:
            items.append(
                {
                    "headline": summary.headline,
                    "teaser": summary.teaser,
                    "takeaway": summary.takeaway,
                    "bullets": summary.bullets_json,
                    "citations": summary.citations_json,
                }
            )

    return items


async def send_digest_to_ready_users(
    db: AsyncSession,
    issue_date: date,
) -> dict:
    """Send digest to all users whose delivery window is active.

    This function should be called frequently (every 15 min) by the scheduler.
    It only sends to users who:
    - Are subscribed
    - Haven't received this issue yet
    - Are in their delivery window (or window has passed for catch-up)

    Args:
        db: Database session
        issue_date: The issue date to send

    Returns:
        Dict with sent_count, skipped_count, error_count
    """
    # Check if issue exists for today
    items = await get_issue_items_for_date(db, issue_date)
    if not items:
        logger.bind(issue_date=str(issue_date)).debug("no_issue_for_date")
        return {"sent_count": 0, "skipped_count": 0, "error_count": 0, "no_issue": True}

    # Get "You may have missed" items
    missed_clusters = await get_missed_from_yesterday(db, limit=3)
    missed_items = [
        {"headline": c.summary.headline, "teaser": c.summary.teaser}
        for c in missed_clusters
        if c.summary
    ]

    # Get users ready for delivery
    ready_users = await get_users_ready_for_delivery(db, issue_date)

    if not ready_users:
        logger.debug("no_users_ready_for_delivery")
        return {"sent_count": 0, "skipped_count": 0, "error_count": 0}

    sent_count = 0
    error_count = 0

    for user in ready_users:
        try:
            await send_daily_digest(
                email=user.email,
                issue_date=str(issue_date),
                items=items,
                missed_items=missed_items,
            )
            await record_delivery(db, user, issue_date)
            sent_count += 1

            logger.bind(
                email=user.email,
                timezone=user.timezone,
                issue_date=str(issue_date),
            ).info("digest_delivered")

        except Exception as e:
            error_count += 1
            logger.bind(
                email=user.email,
                error=str(e),
            ).error("digest_delivery_failed")

    await db.commit()

    return {
        "sent_count": sent_count,
        "skipped_count": 0,
        "error_count": error_count,
    }


async def send_digest_immediately(
    db: AsyncSession,
    user: User,
    issue_date: date,
) -> bool:
    """Send digest to a user immediately (for catch-up on new signup).

    Args:
        db: Database session
        user: The user to send to
        issue_date: The issue date to send

    Returns:
        True if sent successfully, False otherwise
    """
    # Check if already delivered
    existing = await db.execute(
        select(DigestDelivery).where(
            and_(
                DigestDelivery.user_id == user.id,
                DigestDelivery.issue_date == issue_date,
            )
        )
    )
    if existing.scalar_one_or_none():
        logger.bind(email=user.email, issue_date=str(issue_date)).debug("digest_already_delivered")
        return False

    # Get issue items
    items = await get_issue_items_for_date(db, issue_date)
    if not items:
        return False

    # Get missed items
    missed_clusters = await get_missed_from_yesterday(db, limit=3)
    missed_items = [
        {"headline": c.summary.headline, "teaser": c.summary.teaser}
        for c in missed_clusters
        if c.summary
    ]

    try:
        await send_daily_digest(
            email=user.email,
            issue_date=str(issue_date),
            items=items,
            missed_items=missed_items,
        )
        await record_delivery(db, user, issue_date)
        await db.commit()

        logger.bind(
            email=user.email,
            issue_date=str(issue_date),
        ).info("digest_delivered_immediately")
        return True

    except Exception as e:
        logger.bind(email=user.email, error=str(e)).error("immediate_delivery_failed")
        return False
