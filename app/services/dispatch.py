"""
Dispatch service for sending digests to multiple destinations.

Provides an extensible registry pattern for adding new destinations
(Discord, email, Slack, etc.) without modifying core logic.
"""

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_config, get_settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.cluster import Cluster, ClusterSummary
from app.models.issue import Issue
from app.models.user import User
from app.pipeline.issue_builder import get_missed_from_yesterday
from app.services.discord_service import send_discord_digest
from app.services.email_service import send_daily_digest
from app.services.twitter_service import send_twitter_digest

logger = get_logger(__name__)


@dataclass
class DispatchResult:
    """Result of dispatching to a single destination."""

    destination: str
    success: bool
    message: str


class Destination(Protocol):
    """Protocol for dispatch destinations."""

    name: str

    async def send(self, issue_date: date, items: list[dict]) -> DispatchResult:
        """Send digest to this destination."""
        ...


class DiscordDestination:
    """Discord destination using webhook."""

    name = "discord"

    async def send(self, issue_date: date, items: list[dict]) -> DispatchResult:
        try:
            success = await send_discord_digest(issue_date, items)
            if success:
                return DispatchResult(
                    destination=self.name,
                    success=True,
                    message=f"Posted {len(items)} items to Discord",
                )
            else:
                config = get_config()
                if not config.discord.enabled:
                    return DispatchResult(
                        destination=self.name,
                        success=False,
                        message="Discord is disabled in config",
                    )
                return DispatchResult(
                    destination=self.name,
                    success=False,
                    message="Discord webhook failed",
                )
        except Exception as e:
            logger.bind(error=str(e)).error("discord_dispatch_error")
            return DispatchResult(
                destination=self.name,
                success=False,
                message=f"Error: {str(e)}",
            )


class EmailDestination:
    """Email destination using Resend."""

    name = "email"

    async def send(self, issue_date: date, items: list[dict]) -> DispatchResult:
        settings = get_settings()

        if not settings.resend_api_key:
            return DispatchResult(
                destination=self.name,
                success=False,
                message="Resend API key not configured",
            )

        sent_count = 0
        errors = []

        async with AsyncSessionLocal() as db:
            # Fetch "You may have missed" items from yesterday
            missed_clusters = await get_missed_from_yesterday(db, limit=3)
            missed_items = [
                {"headline": c.summary.headline, "teaser": c.summary.teaser}
                for c in missed_clusters
                if c.summary
            ]

            result = await db.execute(select(User).where(User.is_subscribed == True))  # noqa: E712
            users = result.scalars().all()

            if not users:
                return DispatchResult(
                    destination=self.name,
                    success=True,
                    message="No subscribed users to send to",
                )

            for user in users:
                try:
                    await send_daily_digest(
                        email=user.email,
                        issue_date=str(issue_date),
                        items=items,
                        missed_items=missed_items,
                    )
                    sent_count += 1
                except Exception as e:
                    errors.append(f"{user.email}: {str(e)}")
                    logger.bind(email=user.email, error=str(e)).error("email_dispatch_error")

        if errors:
            return DispatchResult(
                destination=self.name,
                success=sent_count > 0,
                message=f"Sent {sent_count} emails, {len(errors)} failed",
            )

        return DispatchResult(
            destination=self.name,
            success=True,
            message=f"Sent {sent_count} emails",
        )


class TwitterDestination:
    """Twitter destination using API v2 for thread posting."""

    name = "twitter"

    async def send(self, issue_date: date, items: list[dict]) -> DispatchResult:
        try:
            success = await send_twitter_digest(issue_date, items)
            if success:
                return DispatchResult(
                    destination=self.name,
                    success=True,
                    message=f"Posted thread with {len(items)} stories",
                )
            else:
                config = get_config()
                if not config.twitter.enabled:
                    return DispatchResult(
                        destination=self.name,
                        success=False,
                        message="Twitter is disabled in config",
                    )
                return DispatchResult(
                    destination=self.name,
                    success=False,
                    message="Twitter thread posting failed",
                )
        except Exception as e:
            logger.bind(error=str(e)).error("twitter_dispatch_error")
            return DispatchResult(
                destination=self.name,
                success=False,
                message=f"Error: {str(e)}",
            )


class DispatchRegistry:
    """Registry for dispatch destinations."""

    def __init__(self) -> None:
        self._destinations: dict[str, Destination] = {}

    def register(self, destination: Destination) -> None:
        """Register a destination."""
        self._destinations[destination.name] = destination

    def get(self, name: str) -> Destination | None:
        """Get a destination by name."""
        return self._destinations.get(name)

    def list_available(self) -> list[str]:
        """List all registered destination names."""
        return list(self._destinations.keys())


# Global registry with default destinations
_registry = DispatchRegistry()
_registry.register(DiscordDestination())
_registry.register(EmailDestination())
_registry.register(TwitterDestination())


def get_registry() -> DispatchRegistry:
    """Get the global dispatch registry."""
    return _registry


async def get_issue_items(db: AsyncSession, issue_date: date) -> list[dict]:
    """Fetch issue items for the given date."""
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


async def get_latest_issue_date(db: AsyncSession) -> date | None:
    """Get the most recent issue date."""
    result = await db.execute(select(Issue.issue_date).order_by(Issue.issue_date.desc()).limit(1))
    return result.scalar_one_or_none()


async def dispatch_issue(
    db: AsyncSession,
    issue_date: date,
    destinations: list[str] | None = None,
) -> list[DispatchResult]:
    """
    Dispatch an issue to specified destinations.

    Args:
        db: Database session
        issue_date: Date of the issue to dispatch
        destinations: List of destination names. If None, dispatch to all.

    Returns:
        List of dispatch results for each destination.
    """
    registry = get_registry()

    # Get destinations to use
    if destinations is None:
        destination_names = registry.list_available()
    else:
        destination_names = destinations

    # Fetch items once
    items = await get_issue_items(db, issue_date)

    if not items:
        return [
            DispatchResult(
                destination="all",
                success=False,
                message=f"No items found for {issue_date}",
            )
        ]

    # Dispatch to each destination
    results = []
    for name in destination_names:
        dest = registry.get(name)
        if dest is None:
            results.append(
                DispatchResult(
                    destination=name,
                    success=False,
                    message=f"Unknown destination: {name}",
                )
            )
        else:
            result = await dest.send(issue_date, items)
            results.append(result)
            logger.bind(
                destination=name,
                success=result.success,
                message=result.message,
            ).info("dispatch_result")

    return results
