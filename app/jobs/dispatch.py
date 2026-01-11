"""
Dispatch job for sending stored digests to destinations.

Run with: python -m app.jobs.dispatch
Options:
  --date DATE         Issue date (default: latest)
  --destinations LIST Comma-separated destinations (default: all)

Examples:
  python -m app.jobs.dispatch --destinations discord
  python -m app.jobs.dispatch --date 2026-01-11 --destinations discord,email
"""

import argparse
import asyncio
from datetime import date, datetime

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger, setup_logging
from app.services.dispatch import (
    dispatch_issue,
    get_latest_issue_date,
    get_registry,
)

logger = get_logger(__name__)


async def main(
    issue_date: date | None = None,
    destinations: list[str] | None = None,
) -> None:
    """Run the dispatch job."""
    setup_logging()

    registry = get_registry()
    available = registry.list_available()

    logger.bind(
        requested_date=str(issue_date) if issue_date else "latest",
        destinations=destinations or available,
    ).info("dispatch_job_started")

    async with AsyncSessionLocal() as db:
        # Resolve date
        if issue_date is None:
            issue_date = await get_latest_issue_date(db)
            if issue_date is None:
                logger.error("no_issues_found")
                print("Error: No issues found in database")
                return

        logger.bind(issue_date=str(issue_date)).info("dispatching_issue")

        # Dispatch
        results = await dispatch_issue(db, issue_date, destinations)

        # Print results
        print(f"\nDispatch Results for {issue_date}")
        print("-" * 40)
        for result in results:
            status = "OK" if result.success else "FAILED"
            print(f"  [{status}] {result.destination}: {result.message}")

        success_count = sum(1 for r in results if r.success)
        print(f"\n{success_count}/{len(results)} destinations succeeded")

        logger.bind(
            issue_date=str(issue_date),
            success_count=success_count,
            total_count=len(results),
        ).info("dispatch_job_completed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dispatch stored digest to destinations")
    parser.add_argument(
        "--date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=None,
        help="Issue date (YYYY-MM-DD). Default: latest",
    )
    parser.add_argument(
        "--destinations",
        type=str,
        default=None,
        help="Comma-separated list of destinations. Default: all",
    )
    args = parser.parse_args()

    dest_list = None
    if args.destinations:
        dest_list = [d.strip() for d in args.destinations.split(",") if d.strip()]

    asyncio.run(main(issue_date=args.date, destinations=dest_list))
