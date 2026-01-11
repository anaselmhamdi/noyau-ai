"""
Hourly ingest job.

Run with: python -m app.jobs.hourly

This job:
1. Fetches content from all configured sources
2. Upserts content items to the database
3. Creates metrics snapshots for engagement tracking
"""

import asyncio

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger, setup_logging
from app.ingest.orchestrator import run_hourly_ingest

logger = get_logger(__name__)


async def main() -> None:
    """Run the hourly ingest job."""
    setup_logging()
    logger.info("hourly_job_started")

    async with AsyncSessionLocal() as db:
        try:
            stats = await run_hourly_ingest(db)
            logger.bind(**stats).info("hourly_job_completed")
        except Exception as e:
            logger.bind(error=str(e)).error("hourly_job_failed")
            raise


if __name__ == "__main__":
    asyncio.run(main())
