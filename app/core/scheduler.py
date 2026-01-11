"""
APScheduler integration for FastAPI.

Runs hourly ingest and daily digest jobs in-process with PostgreSQL persistence.
"""

from datetime import datetime
from typing import Any

from apscheduler import AsyncScheduler, ConflictPolicy, JobOutcome, JobReleased
from apscheduler.datastores.sqlalchemy import SQLAlchemyDataStore
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.core.database import AsyncSessionLocal, engine
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


async def daily_job() -> None:
    """Daily digest job - builds issue and sends emails."""
    # Import here to avoid circular imports
    from app.jobs.daily import main as run_daily_job

    logger.info("scheduled_daily_job_started")
    try:
        await run_daily_job(dry_run=False)
        logger.info("scheduled_daily_job_completed")
    except Exception as e:
        logger.bind(error=str(e)).error("scheduled_daily_job_failed")
        raise  # Re-raise so APScheduler records the failure


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

    # Use PostgreSQL for job persistence and schedule coordination
    data_store = SQLAlchemyDataStore(engine)
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

    # Daily job: 6:00 UTC
    await scheduler.add_schedule(
        daily_job,
        CronTrigger(hour=6, minute=0),
        id="daily_digest",
        conflict_policy=ConflictPolicy.replace,
    )

    logger.info("scheduler_started", jobs=["hourly_ingest", "daily_digest"])

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
