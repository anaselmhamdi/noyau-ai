"""
Daily issue build job.

Run with: python -m app.jobs.daily
Dry run:  python -m app.jobs.daily --dry-run

This job:
1. Loads content items from the last 36 hours
2. Filters political content
3. Clusters items by canonical identity
4. Scores and ranks clusters
5. Distills top 10 clusters with LLM
6. Saves issue to database (skipped with --dry-run)
7. Writes public JSON for static site (skipped with --dry-run)
8. Sends daily digest emails (skipped with --dry-run)
9. Generates short-form videos for top 3 stories (if enabled)
"""

import argparse
import asyncio
import json
from datetime import date

from sqlalchemy import select

from app.config import get_config, get_settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger, setup_logging
from app.models.cluster import Cluster, ClusterSummary
from app.models.user import User
from app.pipeline.issue_builder import build_daily_issue, get_missed_from_yesterday
from app.services.discord_service import send_discord_digest
from app.services.email_service import send_daily_digest
from app.video.orchestrator import generate_videos_for_issue

logger = get_logger(__name__)


async def get_issue_items(issue_date: date) -> list[dict]:
    """Fetch issue items for the given date."""
    async with AsyncSessionLocal() as db:
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


async def send_digest_emails(issue_date: date, items: list[dict]) -> int:
    """Send daily digest emails to all subscribers."""
    settings = get_settings()

    if not settings.resend_api_key:
        logger.warning("resend_api_key_not_set_skipping_emails")
        return 0

    sent_count = 0

    async with AsyncSessionLocal() as db:
        # Fetch "You may have missed" items from yesterday
        missed_clusters = await get_missed_from_yesterday(db, limit=3)
        missed_items = [
            {"headline": c.summary.headline, "teaser": c.summary.teaser}
            for c in missed_clusters
            if c.summary
        ]

        # Get all users
        result = await db.execute(select(User))
        users = result.scalars().all()

        # Send to each user
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
                logger.bind(email=user.email, error=str(e)).error("email_send_failed")

    return sent_count


def format_preview_output(ranked_with_summaries: list) -> str:
    """Format dry-run output as JSON for preview."""
    items = []
    for rank, (identity, content_items, score_info, summary) in enumerate(
        ranked_with_summaries, start=1
    ):
        if summary:
            output = summary.output
            items.append(
                {
                    "rank": rank,
                    "headline": output.headline,
                    "teaser": output.teaser,
                    "takeaway": output.takeaway,
                    "why_care": output.why_care,
                    "bullets": output.bullets,
                    "citations": [c.model_dump() for c in output.citations],
                    "confidence": output.confidence,
                    "score": score_info.get("score"),
                    "tokens": {
                        "prompt": summary.prompt_tokens,
                        "completion": summary.completion_tokens,
                        "total": summary.total_tokens,
                    },
                }
            )

    return json.dumps(
        {"date": str(date.today()), "items": items},
        indent=2,
        ensure_ascii=False,
    )


async def main(dry_run: bool = False) -> None:
    """Run the daily issue build job."""
    setup_logging()
    logger.bind(dry_run=dry_run).info("daily_job_started")

    issue_date = date.today()

    async with AsyncSessionLocal() as db:
        try:
            # Build the issue
            result = await build_daily_issue(db, issue_date, dry_run=dry_run)

            if dry_run:
                # Print preview to stdout
                ranked_with_summaries = result.get("ranked_with_summaries", [])
                print(format_preview_output(ranked_with_summaries))
                logger.bind(**result.get("stats", {})).info("dry_run_completed")
                return

            logger.bind(**result.get("stats", {})).info("daily_build_completed")

            # Fetch items for distribution
            items = await get_issue_items(issue_date)

            # Send emails
            sent_count = await send_digest_emails(issue_date, items)
            logger.bind(count=sent_count).info("emails_sent")

            # Post to Discord
            try:
                discord_sent = await send_discord_digest(issue_date, items)
                if discord_sent:
                    logger.info("discord_digest_sent")
            except Exception as e:
                # Don't fail the job for Discord errors
                logger.bind(error=str(e)).error("discord_send_failed")

            # Generate videos for top stories (if enabled)
            config = get_config()
            if config.video.enabled:
                try:
                    ranked_with_summaries = result.get("ranked_with_summaries", [])
                    video_results = await generate_videos_for_issue(
                        issue_date=issue_date,
                        ranked_with_summaries=ranked_with_summaries,
                        db=db,
                        dry_run=False,
                    )
                    logger.bind(
                        videos_generated=len(video_results),
                        videos_published=sum(1 for v in video_results if v.youtube_video_id),
                    ).info("videos_generated")
                except Exception as e:
                    # Don't fail the job for video generation errors
                    logger.bind(error=str(e)).error("video_generation_failed")

            logger.info("daily_job_completed")

        except Exception as e:
            logger.bind(error=str(e)).error("daily_job_failed")
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the daily issue build job")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the issue without saving to DB or sending emails",
    )
    args = parser.parse_args()

    asyncio.run(main(dry_run=args.dry_run))
