"""
APScheduler integration for FastAPI.

Runs hourly ingest and daily digest jobs in-process with PostgreSQL persistence.

Jobs:
- Hourly ingest: Fetches content from all sources (top of every hour)
- Daily build: Builds the issue at 05:00 UTC (before any user's delivery window)
- Podcast generate: Generates daily podcast at 05:30 UTC (after daily build)
- Delivery window: Sends digests to users every 15 min based on their timezone
"""

from datetime import date, datetime
from typing import Any

from apscheduler import AsyncScheduler, ConflictPolicy, JobOutcome, JobReleased
from apscheduler.datastores.memory import MemoryDataStore
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.ingest.orchestrator import run_hourly_ingest

logger = get_logger(__name__)

# Global scheduler instance
scheduler: AsyncScheduler | None = None


async def hourly_job() -> None:
    """Hourly ingest job - fetches content from all sources."""
    logger.info("scheduled_hourly_job_started")
    async with AsyncSessionLocal() as db:
        try:
            stats = await run_hourly_ingest(db)
            logger.bind(**stats).info("scheduled_hourly_job_completed")
        except Exception as e:
            logger.bind(error=str(e)).error("scheduled_hourly_job_failed")
            raise  # Re-raise so APScheduler records the failure


async def daily_build_job() -> None:
    """Daily build job - builds issue and dispatches to social channels.

    Runs at 05:00 UTC to ensure the issue is ready before any user's
    delivery window starts. Email dispatch is handled separately by
    the delivery_window_job.
    """
    # Import here to avoid circular imports
    from app.jobs.daily import main as run_daily_job

    logger.info("scheduled_daily_build_started")
    try:
        await run_daily_job(dry_run=False, skip_email=True)
        logger.info("scheduled_daily_build_completed")
    except Exception as e:
        logger.bind(error=str(e)).error("scheduled_daily_build_failed")
        raise


async def delivery_window_job() -> None:
    """Delivery window job - sends digests to users in their delivery window.

    Runs every 15 minutes. Checks which users should receive the digest
    based on their timezone and preferred delivery time, then sends
    to those whose window is active or has passed (catch-up logic).
    """
    from app.services.digest_dispatch import send_digest_to_ready_users

    logger.debug("delivery_window_job_started")
    async with AsyncSessionLocal() as db:
        try:
            issue_date = date.today()
            result = await send_digest_to_ready_users(db, issue_date)

            if result.get("no_issue"):
                logger.debug("delivery_window_no_issue")
                return

            if result["sent_count"] > 0 or result["error_count"] > 0:
                logger.bind(
                    sent=result["sent_count"],
                    errors=result["error_count"],
                ).info("delivery_window_job_completed")
            else:
                logger.debug("delivery_window_no_users_ready")

        except Exception as e:
            logger.bind(error=str(e)).error("delivery_window_job_failed")
            raise


async def podcast_generate_job() -> None:
    """Generate daily podcast from top 5 stories.

    Runs at 05:30 UTC, 30 minutes after the daily build to ensure
    the issue and cluster summaries are ready.
    """
    from app.config import get_config
    from app.jobs.podcast_generate import main as run_podcast_job

    # Check if podcast is enabled
    config = get_config()
    if hasattr(config, "podcast") and config.podcast:
        if not config.podcast.enabled:
            logger.debug("podcast_generation_disabled")
            return

    logger.info("scheduled_podcast_generate_started")
    try:
        await run_podcast_job(dry_run=False)
        logger.info("scheduled_podcast_generate_completed")
    except Exception as e:
        logger.bind(error=str(e)).error("scheduled_podcast_generate_failed")
        raise


# Backwards compatibility alias
async def daily_job() -> None:
    """Daily digest job - builds issue and sends emails.

    DEPRECATED: Use daily_build_job + delivery_window_job instead.
    Kept for backwards compatibility with manual CLI invocation.
    """
    from app.jobs.daily import main as run_daily_job

    logger.info("scheduled_daily_job_started")
    try:
        await run_daily_job(dry_run=False)
        logger.info("scheduled_daily_job_completed")
    except Exception as e:
        logger.bind(error=str(e)).error("scheduled_daily_job_failed")
        raise


async def _record_job_result(
    job_id: str,
    scheduled_at: datetime,
    started_at: datetime,
    outcome: JobOutcome,
    error: str | None = None,
) -> None:
    """Record job execution result to database."""
    from app.models.job_run import JobRun

    async with AsyncSessionLocal() as db:
        job_run = JobRun(
            job_id=job_id,
            scheduled_at=scheduled_at,
            started_at=started_at,
            finished_at=datetime.utcnow(),
            outcome=outcome.name,
            error=error,
        )
        db.add(job_run)
        await db.commit()


async def start_scheduler() -> AsyncScheduler | None:
    """Initialize and start the scheduler with PostgreSQL persistence."""
    global scheduler

    settings = get_settings()
    if not settings.scheduler_enabled:
        logger.info("scheduler_disabled_by_config")
        return None

    # Use in-memory storage to avoid Neon connection drop crashes
    # Trade-off: schedules don't persist across restarts, but scheduler won't crash
    data_store = MemoryDataStore()
    scheduler = AsyncScheduler(data_store=data_store)

    # Start the scheduler first (required before calling other methods in APScheduler 4.x)
    await scheduler.__aenter__()

    # Subscribe to job events for history tracking
    scheduler.subscribe(_on_job_completed)

    # Hourly job: top of every hour
    await scheduler.add_schedule(
        hourly_job,
        CronTrigger(minute=0),
        id="hourly_ingest",
        conflict_policy=ConflictPolicy.replace,  # Update if already exists
    )

    # Daily build job: 05:00 UTC (before any user's delivery window)
    # This builds the issue and dispatches to social channels (not email)
    await scheduler.add_schedule(
        daily_build_job,
        CronTrigger(hour=5, minute=0),
        id="daily_build",
        conflict_policy=ConflictPolicy.replace,
    )

    # Podcast generate job: 05:30 UTC (after daily build)
    # Generates daily podcast from top 5 stories
    await scheduler.add_schedule(
        podcast_generate_job,
        CronTrigger(hour=5, minute=30),
        id="podcast_generate",
        conflict_policy=ConflictPolicy.replace,
    )

    # Delivery window job: every 15 minutes
    # Sends digest emails to users based on their timezone preferences
    await scheduler.add_schedule(
        delivery_window_job,
        CronTrigger(minute="*/15"),
        id="delivery_window",
        conflict_policy=ConflictPolicy.replace,
    )

    # Start the scheduler's background worker to actually process jobs
    await scheduler.start_in_background()

    logger.info(
        "scheduler_started",
        jobs=["hourly_ingest", "daily_build", "podcast_generate", "delivery_window"],
    )

    return scheduler


async def _on_job_completed(event: Any) -> None:
    """Handle job completion events."""
    if isinstance(event, JobReleased):
        try:
            scheduled_at = getattr(event, "scheduled_fire_time", None) or datetime.utcnow()
            started_at = getattr(event, "started_at", None) or datetime.utcnow()
            exception = getattr(event, "exception", None)
            await _record_job_result(
                job_id=event.schedule_id or "unknown",
                scheduled_at=scheduled_at,
                started_at=started_at,
                outcome=event.outcome,
                error=str(exception) if event.outcome == JobOutcome.error and exception else None,
            )
        except Exception as e:
            logger.bind(error=str(e)).error("failed_to_record_job_result")


async def stop_scheduler() -> None:
    """Gracefully stop the scheduler."""
    global scheduler
    if scheduler:
        await scheduler.__aexit__(None, None, None)
        logger.info("scheduler_stopped")
        scheduler = None


async def get_job_schedules() -> list[dict[str, Any]]:
    """Get all registered job schedules."""
    if not scheduler:
        return []

    schedules = await scheduler.get_schedules()
    return [
        {
            "id": s.id,
            "task_id": s.task_id,
            "trigger": str(s.trigger),
            "next_fire_time": s.next_fire_time.isoformat() if s.next_fire_time else None,
            "last_fire_time": s.last_fire_time.isoformat() if s.last_fire_time else None,
        }
        for s in schedules
    ]
