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
8. Generates short-form videos for top 3 stories (if enabled)
9. Generates podcast audio for top 5 stories (if enabled)
10. Dispatches to all channels (email, Discord, Slack, Twitter, TikTok, Instagram)

Note: Video and podcast generation run BEFORE dispatchers so all channels
have access to media URLs.
"""

import argparse
import asyncio
import json
from datetime import date

from sqlalchemy import select

from app.config import get_config, get_settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger, setup_logging
from app.jobs.podcast_generate import generate_podcast_for_issue
from app.models.cluster import Cluster, ClusterSummary
from app.models.user import User
from app.pipeline.issue_builder import build_daily_issue, get_missed_from_yesterday
from app.services.discord_dm_service import send_discord_digests
from app.services.discord_service import send_discord_digest, send_discord_error
from app.services.email_service import send_daily_digest
from app.services.instagram_service import send_instagram_reels
from app.services.slack_dm_service import send_slack_digests
from app.services.tiktok_service import send_tiktok_videos
from app.services.twitter_service import send_twitter_digest
from app.video.orchestrator import generate_videos_for_issue

logger = get_logger(__name__)


async def _notify_dispatch_error(channel: str, error: Exception) -> None:
    """
    Safely attempt to send a Discord error notification for dispatch failures.

    This function never raises - if Discord notification fails, it just logs.
    """
    try:
        await send_discord_error(
            title=f"{channel} Dispatch Failed",
            error=str(error),
            context={"channel": channel, "job": "daily"},
        )
    except Exception as notify_error:
        # Don't let error notification failures propagate
        logger.bind(channel=channel, notify_error=str(notify_error)).warning(
            "failed_to_send_dispatch_error_notification"
        )


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


async def main(dry_run: bool = False, skip_email: bool = False) -> None:
    """Run the daily issue build job.

    Args:
        dry_run: If True, skip database writes and dispatches
        skip_email: If True, skip email dispatch (used by scheduler for separate delivery)
    """
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

            # Get config for channel settings
            config = get_config()

            # Track dispatch results for summary
            dispatch_results: dict[str, bool] = {}

            # =====================================================================
            # GENERATE: Video (YouTube) - must run before dispatchers
            # =====================================================================
            video_results: list = []
            if config.video.enabled:
                try:
                    ranked_with_summaries = result.get("ranked_with_summaries", [])
                    video_results = await generate_videos_for_issue(
                        issue_date=issue_date,
                        ranked_with_summaries=ranked_with_summaries,
                        db=db,
                        dry_run=False,
                    )
                    videos_published = sum(1 for v in video_results if v.youtube_video_id)
                    logger.bind(
                        videos_generated=len(video_results),
                        videos_published=videos_published,
                    ).info("videos_generated")
                    dispatch_results["youtube"] = videos_published > 0
                except Exception as e:
                    logger.bind(error=str(e)).error("video_generation_failed")
                    dispatch_results["youtube"] = False
                    await _notify_dispatch_error("YouTube/Video", e)

            # =====================================================================
            # GENERATE: Podcast - must run before dispatchers
            # =====================================================================
            if hasattr(config, "podcast") and config.podcast and config.podcast.enabled:
                try:
                    podcast_result = await generate_podcast_for_issue(
                        db=db,
                        issue_date=issue_date,
                        skip_video=False,
                    )
                    if podcast_result.get("success"):
                        logger.bind(
                            audio_url=podcast_result.get("audio_url"),
                            duration=podcast_result.get("duration_seconds"),
                        ).info("podcast_generated")
                    dispatch_results["podcast"] = podcast_result.get("success", False)
                except Exception as e:
                    logger.bind(error=str(e)).error("podcast_generation_failed")
                    dispatch_results["podcast"] = False
                    await _notify_dispatch_error("Podcast", e)

            # =====================================================================
            # DISPATCH: Email
            # =====================================================================
            if not skip_email:
                try:
                    sent_count = await send_digest_emails(issue_date, items)
                    logger.bind(count=sent_count).info("emails_sent")
                    dispatch_results["email"] = True
                except Exception as e:
                    logger.bind(error=str(e)).error("email_send_failed")
                    dispatch_results["email"] = False
                    await _notify_dispatch_error("Email", e)
            else:
                logger.info("email_dispatch_skipped")

            # =====================================================================
            # DISPATCH: Discord (channel webhook)
            # =====================================================================
            try:
                discord_sent = await send_discord_digest(issue_date, items)
                if discord_sent:
                    logger.info("discord_digest_sent")
                dispatch_results["discord"] = discord_sent
            except Exception as e:
                logger.bind(error=str(e)).error("discord_send_failed")
                dispatch_results["discord"] = False
                await _notify_dispatch_error("Discord", e)

            # =====================================================================
            # DISPATCH: Discord DMs (bot subscriptions)
            # =====================================================================
            if config.discord_bot.enabled:
                try:
                    dm_result = await send_discord_digests(issue_date, items)
                    if dm_result.sent > 0:
                        logger.bind(sent=dm_result.sent, failed=dm_result.failed).info(
                            "discord_dms_sent"
                        )
                    dispatch_results["discord_dm"] = dm_result.success
                except Exception as e:
                    logger.bind(error=str(e)).error("discord_dm_send_failed")
                    dispatch_results["discord_dm"] = False
                    await _notify_dispatch_error("Discord DM", e)

            # =====================================================================
            # DISPATCH: Slack DMs
            # =====================================================================
            if config.slack.enabled:
                try:
                    slack_result = await send_slack_digests(issue_date, items)
                    if slack_result.sent > 0:
                        logger.bind(sent=slack_result.sent, failed=slack_result.failed).info(
                            "slack_dms_sent"
                        )
                    dispatch_results["slack_dm"] = slack_result.success
                except Exception as e:
                    logger.bind(error=str(e)).error("slack_dm_send_failed")
                    dispatch_results["slack_dm"] = False
                    await _notify_dispatch_error("Slack DM", e)

            # =====================================================================
            # DISPATCH: Twitter
            # =====================================================================
            if config.twitter.enabled:
                try:
                    twitter_sent = await send_twitter_digest(issue_date, items)
                    if twitter_sent:
                        logger.info("twitter_digest_sent")
                    dispatch_results["twitter"] = twitter_sent
                except Exception as e:
                    logger.bind(error=str(e)).error("twitter_send_failed")
                    dispatch_results["twitter"] = False
                    await _notify_dispatch_error("Twitter", e)

            # =====================================================================
            # DISPATCH: TikTok
            # =====================================================================
            if config.tiktok.enabled and video_results:
                try:
                    videos_for_social = [
                        {"s3_url": v.s3_url, "youtube_url": v.youtube_url}
                        for v in video_results
                        if v.s3_url
                    ]
                    tiktok_result = await send_tiktok_videos(issue_date, videos_for_social, items)
                    if tiktok_result.success:
                        logger.bind(message=tiktok_result.message).info("tiktok_videos_posted")
                    dispatch_results["tiktok"] = tiktok_result.success
                except Exception as e:
                    logger.bind(error=str(e)).error("tiktok_send_failed")
                    dispatch_results["tiktok"] = False
                    await _notify_dispatch_error("TikTok", e)

            # =====================================================================
            # DISPATCH: Instagram Reels
            # =====================================================================
            if config.instagram.enabled and video_results:
                try:
                    videos_for_social = [
                        {"s3_url": v.s3_url, "youtube_url": v.youtube_url}
                        for v in video_results
                        if v.s3_url
                    ]
                    instagram_result = await send_instagram_reels(
                        issue_date, videos_for_social, items
                    )
                    if instagram_result.success:
                        logger.bind(message=instagram_result.message).info("instagram_reels_posted")
                    dispatch_results["instagram"] = instagram_result.success
                except Exception as e:
                    logger.bind(error=str(e)).error("instagram_send_failed")
                    dispatch_results["instagram"] = False
                    await _notify_dispatch_error("Instagram", e)

            # Log dispatch summary
            successful = [k for k, v in dispatch_results.items() if v]
            failed = [k for k, v in dispatch_results.items() if not v]
            logger.bind(successful=successful, failed=failed).info("daily_job_completed")

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
