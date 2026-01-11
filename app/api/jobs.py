"""Job monitoring API endpoints."""

from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.core.scheduler import get_job_schedules
from app.dependencies import DBSession
from app.models.job_run import JobRun

router = APIRouter()


class ScheduleResponse(BaseModel):
    """Response model for a job schedule."""

    id: str
    task_id: str
    trigger: str
    next_fire_time: str | None
    last_fire_time: str | None


class JobRunResponse(BaseModel):
    """Response model for a job run."""

    id: str
    job_id: str
    scheduled_at: datetime
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    outcome: str
    error: str | None


class JobStatsResponse(BaseModel):
    """Response model for job statistics."""

    job_id: str
    total_runs: int
    successful_runs: int
    failed_runs: int
    success_rate: float
    avg_duration_seconds: float | None
    last_run: datetime | None
    last_outcome: str | None


@router.get("/jobs/schedules", response_model=list[ScheduleResponse])
async def list_schedules() -> list[ScheduleResponse]:
    """
    List all registered job schedules.

    Returns schedule information including next/last fire times.
    """
    schedules = await get_job_schedules()
    return [ScheduleResponse(**s) for s in schedules]


@router.get("/jobs/runs", response_model=list[JobRunResponse])
async def list_job_runs(
    db: DBSession,
    job_id: str | None = Query(default=None, description="Filter by job ID"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[JobRunResponse]:
    """
    List job execution history.

    Returns recent job runs with optional filtering by job ID.
    """
    query = select(JobRun).order_by(JobRun.scheduled_at.desc())

    if job_id:
        query = query.where(JobRun.job_id == job_id)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    runs = result.scalars().all()

    return [
        JobRunResponse(
            id=run.id,
            job_id=run.job_id,
            scheduled_at=run.scheduled_at,
            started_at=run.started_at,
            finished_at=run.finished_at,
            duration_seconds=(run.finished_at - run.started_at).total_seconds(),
            outcome=run.outcome,
            error=run.error,
        )
        for run in runs
    ]


@router.get("/jobs/stats", response_model=list[JobStatsResponse])
async def get_job_stats(db: DBSession) -> list[JobStatsResponse]:
    """
    Get aggregated statistics for all jobs.

    Returns success rates, average durations, and last run info.
    """
    # Get distinct job IDs
    job_ids_result = await db.execute(select(JobRun.job_id).distinct())
    job_ids = job_ids_result.scalars().all()

    stats = []
    for job_id in job_ids:
        # Total and successful counts
        total_result = await db.execute(
            select(func.count(JobRun.id)).where(JobRun.job_id == job_id)
        )
        total = total_result.scalar() or 0

        success_result = await db.execute(
            select(func.count(JobRun.id)).where(
                JobRun.job_id == job_id, JobRun.outcome == "success"
            )
        )
        successful = success_result.scalar() or 0

        # Average duration for successful runs
        avg_result = await db.execute(
            select(
                func.avg(
                    func.extract("epoch", JobRun.finished_at)
                    - func.extract("epoch", JobRun.started_at)
                )
            ).where(JobRun.job_id == job_id, JobRun.outcome == "success")
        )
        avg_duration = avg_result.scalar()

        # Last run
        last_run_result = await db.execute(
            select(JobRun)
            .where(JobRun.job_id == job_id)
            .order_by(JobRun.scheduled_at.desc())
            .limit(1)
        )
        last_run = last_run_result.scalar_one_or_none()

        stats.append(
            JobStatsResponse(
                job_id=job_id,
                total_runs=total,
                successful_runs=successful,
                failed_runs=total - successful,
                success_rate=successful / total if total > 0 else 0.0,
                avg_duration_seconds=float(avg_duration) if avg_duration else None,
                last_run=last_run.scheduled_at if last_run else None,
                last_outcome=last_run.outcome if last_run else None,
            )
        )

    return stats
