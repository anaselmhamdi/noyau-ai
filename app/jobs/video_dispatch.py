"""
Video dispatch job for posting existing videos to social platforms.

Run with: python -m app.jobs.video_dispatch
Options:
  --date DATE         Issue date (default: today)
  --destinations LIST Comma-separated destinations: youtube, tiktok, instagram (default: all)

Examples:
  python -m app.jobs.video_dispatch
  python -m app.jobs.video_dispatch --date 2026-01-13
  python -m app.jobs.video_dispatch --destinations instagram
  python -m app.jobs.video_dispatch --date 2026-01-13 --destinations youtube,tiktok,instagram
"""

import argparse
import asyncio
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_config
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger, setup_logging
from app.models.cluster import Cluster, ClusterSummary
from app.models.video import Video, VideoStatus
from app.services.instagram_service import send_instagram_reels
from app.services.tiktok_service import send_tiktok_videos
from app.video.uploader import YouTubeUploader, create_video_metadata

logger = get_logger(__name__)

AVAILABLE_DESTINATIONS = ["youtube", "tiktok", "instagram"]


async def get_videos_for_date(db: AsyncSession, issue_date: date) -> list[Video]:
    """Query videos for the given date."""
    stmt = select(Video).where(Video.issue_date == issue_date).order_by(Video.rank)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def dispatch_youtube(
    db: AsyncSession,
    videos: list[Video],
    items: list[dict],
) -> tuple[bool, str]:
    """Upload videos to YouTube that don't have youtube_video_id yet."""
    # Filter to videos that need YouTube upload
    videos_to_upload = [v for v in videos if v.video_path and not v.youtube_video_id]

    if not videos_to_upload:
        # Check if all videos already have YouTube IDs
        already_uploaded = sum(1 for v in videos if v.youtube_video_id)
        if already_uploaded == len(videos):
            return True, f"All {already_uploaded} videos already uploaded to YouTube"
        return False, "No videos with local files available for upload"

    uploader = YouTubeUploader()

    uploaded = 0
    errors = []

    for video in videos_to_upload:
        video_path = Path(video.video_path)
        if not video_path.exists():
            errors.append(f"Rank {video.rank}: File not found ({video.video_path})")
            continue

        # Get corresponding item for metadata
        if video.rank <= len(items):
            item = items[video.rank - 1]
        else:
            errors.append(f"Rank {video.rank}: No matching item for metadata")
            continue

        # Get topic from script_json if available
        topic = "general"
        if video.script_json and "topic" in video.script_json:
            topic = video.script_json["topic"]

        # Create metadata
        metadata = create_video_metadata(
            headline=item["headline"],
            teaser=item["teaser"],
            topic=topic,
            rank=video.rank,
            citations=item.get("citations"),
        )

        # Upload
        result = await uploader.upload_video(video_path, metadata)
        if result:
            video_id, video_url = result
            video.youtube_video_id = video_id
            video.youtube_url = video_url
            video.status = VideoStatus.PUBLISHED
            await db.commit()
            uploaded += 1
            logger.bind(
                rank=video.rank,
                video_id=video_id,
            ).info("youtube_video_uploaded")
        else:
            errors.append(f"Rank {video.rank}: Upload failed")

    if errors:
        error_msg = "; ".join(errors)
        if uploaded > 0:
            return True, f"Uploaded {uploaded} videos, errors: {error_msg}"
        return False, f"Upload failed: {error_msg}"

    return True, f"Uploaded {uploaded} videos to YouTube"


async def get_issue_items(db: AsyncSession, issue_date: date) -> list[dict]:
    """Query cluster summaries for captions."""
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


async def main(
    issue_date: date | None = None,
    destinations: list[str] | None = None,
) -> None:
    """Run the video dispatch job."""
    setup_logging()

    # Default to today
    if issue_date is None:
        issue_date = date.today()

    # Default to all destinations
    if destinations is None:
        destinations = AVAILABLE_DESTINATIONS.copy()

    # Validate destinations
    invalid = [d for d in destinations if d not in AVAILABLE_DESTINATIONS]
    if invalid:
        print(f"Error: Unknown destinations: {invalid}")
        print(f"Available: {AVAILABLE_DESTINATIONS}")
        return

    logger.bind(
        issue_date=str(issue_date),
        destinations=destinations,
    ).info("video_dispatch_started")

    config = get_config()

    async with AsyncSessionLocal() as db:
        # Fetch videos
        videos = await get_videos_for_date(db, issue_date)
        if not videos:
            print(f"No videos found for {issue_date}")
            logger.bind(issue_date=str(issue_date)).warning("no_videos_found")
            return

        print(f"Found {len(videos)} videos for {issue_date}")

        # Fetch items for captions
        items = await get_issue_items(db, issue_date)
        if not items:
            print(f"No issue items found for {issue_date}")
            logger.bind(issue_date=str(issue_date)).warning("no_items_found")
            return

        print(f"Found {len(items)} items for captions")
        print("-" * 40)

        results: dict[str, tuple[bool, str]] = {}

        # Dispatch to YouTube
        if "youtube" in destinations:
            if not config.video.enabled:
                results["youtube"] = (False, "Video is disabled in config")
            else:
                try:
                    youtube_result = await dispatch_youtube(db, videos, items)
                    results["youtube"] = youtube_result
                except Exception as e:
                    logger.bind(error=str(e)).error("youtube_dispatch_error")
                    results["youtube"] = (False, f"Error: {str(e)}")

        # Get video dicts for TikTok/Instagram (need s3_url)
        videos_for_social = [
            {"s3_url": v.s3_url, "youtube_url": v.youtube_url} for v in videos if v.s3_url
        ]

        # Dispatch to TikTok
        if "tiktok" in destinations:
            if not config.tiktok.enabled:
                results["tiktok"] = (False, "TikTok is disabled in config")
            elif not videos_for_social:
                results["tiktok"] = (False, "No videos with s3_url available")
            else:
                try:
                    tiktok_result = await send_tiktok_videos(issue_date, videos_for_social, items)
                    results["tiktok"] = (tiktok_result.success, tiktok_result.message)
                except Exception as e:
                    logger.bind(error=str(e)).error("tiktok_dispatch_error")
                    results["tiktok"] = (False, f"Error: {str(e)}")

        # Dispatch to Instagram
        if "instagram" in destinations:
            if not config.instagram.enabled:
                results["instagram"] = (False, "Instagram is disabled in config")
            elif not videos_for_social:
                results["instagram"] = (False, "No videos with s3_url available")
            else:
                try:
                    instagram_result = await send_instagram_reels(
                        issue_date, videos_for_social, items
                    )
                    results["instagram"] = (instagram_result.success, instagram_result.message)
                except Exception as e:
                    logger.bind(error=str(e)).error("instagram_dispatch_error")
                    results["instagram"] = (False, f"Error: {str(e)}")

        # Print results
        print(f"\nVideo Dispatch Results for {issue_date}")
        print("-" * 40)
        for dest, (success, message) in results.items():
            status = "OK" if success else "FAILED"
            print(f"  [{status}] {dest}: {message}")

        success_count = sum(1 for s, _ in results.values() if s)
        print(f"\n{success_count}/{len(results)} destinations succeeded")

        logger.bind(
            issue_date=str(issue_date),
            success_count=success_count,
            total_count=len(results),
        ).info("video_dispatch_completed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dispatch videos to social platforms")
    parser.add_argument(
        "--date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=None,
        help="Issue date (YYYY-MM-DD). Default: today",
    )
    parser.add_argument(
        "--destinations",
        type=str,
        default=None,
        help="Comma-separated list of destinations: youtube, tiktok, instagram. Default: all",
    )
    args = parser.parse_args()

    dest_list = None
    if args.destinations:
        dest_list = [d.strip() for d in args.destinations.split(",") if d.strip()]

    asyncio.run(main(issue_date=args.date, destinations=dest_list))
