"""
Podcast generation job for creating daily audio digests.

Run with: python -m app.jobs.podcast_generate
Options:
  --date DATE         Issue date (default: today)
  --output-dir PATH   Output directory for podcast files (default: temp directory)
  --dry-run           Preview without generating audio
  --skip-youtube      Skip YouTube upload
  --skip-video        Skip video generation (audio only)

Examples:
  python -m app.jobs.podcast_generate
  python -m app.jobs.podcast_generate --date 2026-01-13
  python -m app.jobs.podcast_generate --dry-run
  python -m app.jobs.podcast_generate --skip-video
  python -m app.jobs.podcast_generate --output-dir /tmp/podcasts
"""

import argparse
import asyncio
import shutil
import tempfile
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_config
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger, setup_logging
from app.models.cluster import Cluster, ClusterSummary
from app.models.issue import Issue
from app.podcast.audio_generator import PodcastAudioGenerator
from app.podcast.rss_feed import generate_podcast_rss, get_default_feed_config
from app.podcast.script_generator import generate_podcast_script
from app.podcast.video_generator import generate_podcast_video
from app.schemas.common import Citation
from app.schemas.llm import ClusterDistillOutput
from app.services.storage_service import get_storage_service

logger = get_logger(__name__)


def summary_to_distill_output(summary: ClusterSummary) -> ClusterDistillOutput:
    """Convert a ClusterSummary to ClusterDistillOutput for script generation."""
    citations = [
        Citation(url=c.get("url", ""), label=c.get("label", "Source"))
        for c in (summary.citations_json or [])
    ]
    if not citations:
        citations = [Citation(url="https://noyau.news", label="Noyau News")]

    bullets = summary.bullets_json or []
    if len(bullets) < 2:
        bullets = bullets + ["See full story for details."] * (2 - len(bullets))
    elif len(bullets) > 2:
        bullets = bullets[:2]

    return ClusterDistillOutput(
        headline=summary.headline,
        teaser=summary.teaser,
        takeaway=summary.takeaway,
        why_care=summary.why_care,
        bullets=bullets,
        citations=citations,
        confidence=summary.confidence.value,
    )


async def get_clusters_for_date(db: AsyncSession, issue_date: date) -> list[Cluster]:
    """Query clusters with summaries for the given date."""
    stmt = (
        select(Cluster)
        .options(selectinload(Cluster.summary))
        .where(Cluster.issue_date == issue_date)
        .order_by(Cluster.cluster_score.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_issue_for_date(db: AsyncSession, issue_date: date) -> Issue | None:
    """Get Issue record for the given date."""
    stmt = select(Issue).where(Issue.issue_date == issue_date)
    result = await db.execute(stmt)
    issue: Issue | None = result.scalar_one_or_none()
    return issue


def determine_topic(cluster: Cluster) -> str:
    """Determine topic from cluster."""
    if cluster.dominant_topic:
        topic = cluster.dominant_topic.value
        if topic in ("security",):
            return "security"
        elif topic in ("oss",):
            return "oss"
        elif topic in ("macro", "deepdive"):
            return "ai"
    return "general"


async def upload_podcast_to_s3(
    audio_path: Path,
    issue_date: date,
) -> str | None:
    """Upload podcast audio to S3."""
    storage = get_storage_service()
    if not storage.is_configured():
        logger.warning("s3_not_configured_skipping_podcast_upload")
        return None

    key = f"podcasts/{issue_date.isoformat()}/noyau_daily.mp3"

    url = await storage.upload_file(
        file_path=audio_path,
        key=key,
        content_type="audio/mpeg",
        public=True,
        metadata={
            "issue_date": issue_date.isoformat(),
            "type": "podcast",
        },
    )

    if url:
        logger.bind(url=url).info("podcast_uploaded_to_s3")

    return url


async def get_episodes_for_rss(db: AsyncSession, limit: int = 50) -> list[dict]:
    """Get podcast episodes for RSS feed generation."""
    stmt = (
        select(Issue)
        .where(Issue.podcast_audio_url.isnot(None))
        .order_by(Issue.issue_date.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    issues = list(result.scalars().all())

    episodes = []
    for i, issue in enumerate(issues):
        episode_number = len(issues) - i  # Count backwards from total
        episodes.append(
            {
                "issue_date": issue.issue_date,
                "episode_number": episode_number,
                "audio_url": issue.podcast_audio_url,
                "duration_seconds": issue.podcast_duration_seconds or 480,  # Default 8 min
                "published_at": issue.created_at,
            }
        )

    return episodes


async def generate_podcast_for_issue(
    db: AsyncSession,
    issue_date: date,
    skip_video: bool = False,
) -> dict:
    """Generate podcast for a given issue date.

    This function is called from daily.py after video generation.

    Args:
        db: Database session
        issue_date: Date of the issue
        skip_video: Whether to skip video generation

    Returns:
        Dict with generation results
    """
    # Get podcast config
    config = get_config()
    story_count = 5

    if hasattr(config, "podcast") and config.podcast:
        podcast_cfg = config.podcast
        if not podcast_cfg.enabled:
            logger.info("podcast_disabled_in_config")
            return {"success": False, "reason": "disabled"}
        story_count = podcast_cfg.story_count

    output_dir = Path(tempfile.mkdtemp(prefix=f"noyau_podcast_{issue_date}_"))

    logger.bind(
        issue_date=str(issue_date),
        story_count=story_count,
        skip_video=skip_video,
    ).info("podcast_generate_started")

    # Check if podcast already exists
    issue = await get_issue_for_date(db, issue_date)
    if not issue:
        logger.warning("no_issue_found_for_date")
        return {"success": False, "reason": "no_issue"}

    if issue.podcast_audio_url:
        logger.info("podcast_already_exists")
        return {"success": True, "audio_url": issue.podcast_audio_url, "already_exists": True}

    # Fetch clusters with summaries
    clusters = await get_clusters_for_date(db, issue_date)
    clusters_with_summaries = [c for c in clusters if c.summary]

    if not clusters_with_summaries:
        logger.warning("no_summaries_found")
        return {"success": False, "reason": "no_summaries"}

    # Take top N for podcast
    top_clusters = clusters_with_summaries[:story_count]

    # Convert to distill outputs
    summaries = []
    topics = []
    for cluster in top_clusters:
        summaries.append(summary_to_distill_output(cluster.summary))
        topics.append(determine_topic(cluster))

    # Step 1: Generate script
    script_result = await generate_podcast_script(summaries, topics, issue_date)

    if not script_result:
        logger.error("podcast_script_generation_failed")
        return {"success": False, "reason": "script_failed"}

    script = script_result.script
    logger.bind(
        story_count=len(script.stories),
        tokens=script_result.total_tokens,
    ).info("podcast_script_generated")

    # Step 2: Generate audio
    generator = PodcastAudioGenerator(
        voice="nova",
        model="tts-1-hd",
        background_volume=0.03,
    )

    audio_path = output_dir / "noyau_daily.mp3"
    audio_result = await generator.generate(
        script=script,
        output_path=audio_path,
        include_background_music=True,
    )

    if not audio_result:
        logger.error("podcast_audio_generation_failed")
        return {"success": False, "reason": "audio_failed"}

    duration_min = audio_result.duration_seconds / 60
    logger.bind(duration_min=duration_min).info("podcast_audio_generated")

    # Step 3: Upload to S3
    s3_url = await upload_podcast_to_s3(audio_path, issue_date)

    # Step 4: Generate video with waveform (if not skipped)
    video_s3_url = None
    if not skip_video:
        video_path = output_dir / "noyau_daily.mp4"

        bg_path: Path | None = None
        for ext in ("png", "jpg"):
            candidate = Path(f"ui/public/podcast-video-bg.{ext}")
            if candidate.exists():
                bg_path = candidate
                break

        count_stmt = select(func.count()).where(Issue.podcast_audio_url.isnot(None))
        count_result = await db.execute(count_stmt)
        episode_number = (count_result.scalar() or 0) + 1

        video_result = generate_podcast_video(
            audio_path=audio_path,
            output_path=video_path,
            episode_number=episode_number,
            issue_date=issue_date,
            background_image_path=bg_path,
        )

        if video_result:
            storage = get_storage_service()
            if storage.is_configured():
                video_key = f"podcasts/{issue_date.isoformat()}/noyau_daily.mp4"
                video_s3_url = await storage.upload_file(
                    file_path=video_path,
                    key=video_key,
                    content_type="video/mp4",
                    public=True,
                    metadata={
                        "issue_date": issue_date.isoformat(),
                        "type": "podcast_video",
                    },
                )

    # Step 5: Update Issue record
    if s3_url:
        issue.podcast_audio_url = s3_url
        issue.podcast_duration_seconds = audio_result.duration_seconds
        await db.commit()

    # Step 6: Regenerate RSS feed
    await regenerate_rss_feed(db, output_dir)

    # Cleanup
    if s3_url:
        shutil.rmtree(output_dir, ignore_errors=True)

    logger.bind(
        issue_date=str(issue_date),
        duration=audio_result.duration_seconds,
        s3_url=s3_url,
    ).info("podcast_generate_completed")

    return {
        "success": True,
        "audio_url": s3_url,
        "duration_seconds": audio_result.duration_seconds,
        "video_url": video_s3_url,
    }


async def regenerate_rss_feed(db: AsyncSession, output_dir: Path) -> None:
    """Regenerate the podcast RSS feed."""
    episodes = await get_episodes_for_rss(db)

    if not episodes:
        logger.warning("no_podcast_episodes_for_rss")
        return

    config = get_default_feed_config()

    # Update config from config.yml if available
    app_config = get_config()
    if hasattr(app_config, "podcast") and app_config.podcast:
        podcast_cfg = app_config.podcast
        if hasattr(podcast_cfg, "feed") and podcast_cfg.feed:
            feed_cfg = podcast_cfg.feed
            config.update(
                {
                    "title": getattr(feed_cfg, "title", config["title"]),
                    "description": getattr(feed_cfg, "description", config["description"]),
                    "author": getattr(feed_cfg, "author", config["author"]),
                    "category": getattr(feed_cfg, "category", config["category"]),
                }
            )

    # Generate RSS feed
    rss_path = output_dir / "feed.xml"
    generate_podcast_rss(episodes, config, rss_path)

    # Upload RSS feed to S3
    storage = get_storage_service()
    if storage.is_configured():
        await storage.upload_file(
            file_path=rss_path,
            key="podcast/feed.xml",
            content_type="application/rss+xml",
            public=True,
        )
        logger.info("podcast_rss_feed_uploaded")


async def main(
    issue_date: date | None = None,
    output_dir: str | None = None,
    dry_run: bool = False,
    skip_youtube: bool = False,
    skip_video: bool = False,
) -> None:
    """Run the podcast generation job."""
    setup_logging()

    if issue_date is None:
        issue_date = date.today()

    # Get podcast config
    config = get_config()
    story_count = 5  # Default

    if hasattr(config, "podcast") and config.podcast:
        podcast_cfg = config.podcast
        if not podcast_cfg.enabled:
            print("Podcast generation is disabled in config")
            return
        story_count = podcast_cfg.story_count

    # Use provided output_dir or create temp directory
    if output_dir:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
    else:
        output_path = Path(tempfile.mkdtemp(prefix=f"noyau_podcast_{issue_date}_"))

    logger.bind(
        issue_date=str(issue_date),
        story_count=story_count,
        dry_run=dry_run,
        skip_video=skip_video,
    ).info("podcast_generate_started")

    async with AsyncSessionLocal() as db:
        # Check if podcast already exists for this date
        issue = await get_issue_for_date(db, issue_date)
        if issue and issue.podcast_audio_url and not dry_run:
            print(f"Podcast already exists for {issue_date}: {issue.podcast_audio_url}")
            logger.warning("podcast_already_exists_for_date")
            return

        if not issue:
            print(f"No issue found for {issue_date}")
            logger.warning("no_issue_found_for_date")
            return

        # Fetch clusters with summaries
        clusters = await get_clusters_for_date(db, issue_date)
        clusters_with_summaries = [c for c in clusters if c.summary]

        if not clusters_with_summaries:
            print(f"No cluster summaries found for {issue_date}")
            logger.warning("no_summaries_found")
            return

        print(f"Found {len(clusters_with_summaries)} clusters with summaries")

        # Take top N for podcast
        top_clusters = clusters_with_summaries[:story_count]
        print(f"Generating podcast for top {len(top_clusters)} stories")
        print("-" * 40)

        # Convert to distill outputs
        summaries = []
        topics = []
        for cluster in top_clusters:
            summaries.append(summary_to_distill_output(cluster.summary))
            topics.append(determine_topic(cluster))
            print(f"  - {cluster.summary.headline[:60]}...")

        # Step 1: Generate script
        print("\nGenerating podcast script...")
        script_result = await generate_podcast_script(summaries, topics, issue_date)

        if not script_result:
            print("Script generation failed")
            logger.error("podcast_script_generation_failed")
            return

        script = script_result.script
        print(f"Script generated: {len(script.stories)} stories")
        logger.bind(
            story_count=len(script.stories),
            tokens=script_result.total_tokens,
        ).info("podcast_script_generated")

        if dry_run:
            print("\n(dry run - skipping audio generation)")
            print("\nScript preview:")
            print(f"Intro: {script.intro[:200]}...")
            for i, story in enumerate(script.stories, 1):
                print(f"\nStory {i}: {story.headline}")
                print(f"  {story.body[:150]}...")
            print(f"\nOutro: {script.outro[:100]}...")
            return

        # Step 2: Generate audio
        print("\nGenerating audio...")
        generator = PodcastAudioGenerator(
            voice="nova",
            model="tts-1-hd",
            background_volume=0.03,
        )

        audio_path = output_path / "noyau_daily.mp3"
        audio_result = await generator.generate(
            script=script,
            output_path=audio_path,
            include_background_music=True,
        )

        if not audio_result:
            print("Audio generation failed")
            logger.error("podcast_audio_generation_failed")
            return

        duration_min = audio_result.duration_seconds / 60
        print(f"Audio generated: {duration_min:.1f} minutes")
        print(f"  Path: {audio_result.audio_path}")
        print(f"  Chapters: {len(audio_result.chapters)}")

        # Step 3: Upload to S3
        print("\nUploading to S3...")
        s3_url = await upload_podcast_to_s3(audio_path, issue_date)

        if s3_url:
            print(f"  S3 URL: {s3_url}")
        else:
            print("  S3 upload skipped (not configured)")

        # Step 4: Generate video with waveform (if not skipped)
        video_path = None
        video_s3_url = None
        if not skip_video:
            print("\nGenerating video with waveform...")
            video_path = output_path / "noyau_daily.mp4"

            # Check for custom background image (try PNG first, then JPG)
            bg_path: Path | None = None
            for ext in ("png", "jpg"):
                candidate = Path(f"ui/public/podcast-video-bg.{ext}")
                if candidate.exists():
                    bg_path = candidate
                    break

            # Count total episodes for episode number
            count_stmt = select(func.count()).where(Issue.podcast_audio_url.isnot(None))
            count_result = await db.execute(count_stmt)
            episode_number = (count_result.scalar() or 0) + 1  # +1 for this new episode

            video_result = generate_podcast_video(
                audio_path=audio_path,
                output_path=video_path,
                episode_number=episode_number,
                issue_date=issue_date,
                background_image_path=bg_path,
            )

            if video_result:
                print(f"  Video generated: {video_result.video_path}")

                # Upload video to S3
                print("  Uploading video to S3...")
                storage = get_storage_service()
                if storage.is_configured():
                    video_key = f"podcasts/{issue_date.isoformat()}/noyau_daily.mp4"
                    video_s3_url = await storage.upload_file(
                        file_path=video_path,
                        key=video_key,
                        content_type="video/mp4",
                        public=True,
                        metadata={
                            "issue_date": issue_date.isoformat(),
                            "type": "podcast_video",
                        },
                    )
                    if video_s3_url:
                        print(f"  Video S3 URL: {video_s3_url}")
            else:
                print("  Video generation failed")
        else:
            print("\nSkipping video generation")

        # Step 5: Upload to YouTube (if not skipped)
        youtube_url = None
        if not skip_youtube and video_path and video_path.exists():
            print("\nUploading to YouTube...")
            # YouTube upload would go here using existing YouTubeUploader
            # from app.video.uploader import YouTubeUploader
            print("  YouTube upload not yet integrated")

        # Step 6: Update Issue record
        if s3_url:
            issue.podcast_audio_url = s3_url
            issue.podcast_youtube_url = youtube_url
            issue.podcast_duration_seconds = audio_result.duration_seconds
            await db.commit()
            print("\nIssue updated with podcast URL")

        # Step 7: Regenerate RSS feed
        print("\nRegenerating RSS feed...")
        await regenerate_rss_feed(db, output_path)

        # Cleanup
        if s3_url:
            print("\nCleaning up local files...")
            shutil.rmtree(output_path)

        # Summary
        print("\n" + "=" * 40)
        print(f"Podcast generated for {issue_date}")
        print(f"  Duration: {duration_min:.1f} minutes")
        if s3_url:
            print(f"  Audio URL: {s3_url}")
        if youtube_url:
            print(f"  YouTube: {youtube_url}")

        logger.bind(
            issue_date=str(issue_date),
            duration=audio_result.duration_seconds,
            s3_url=s3_url,
        ).info("podcast_generate_completed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate podcast from existing issue data")
    parser.add_argument(
        "--date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=None,
        help="Issue date (YYYY-MM-DD). Default: today",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for podcast files. Default: temp directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview script without generating audio",
    )
    parser.add_argument(
        "--skip-youtube",
        action="store_true",
        help="Skip YouTube upload",
    )
    parser.add_argument(
        "--skip-video",
        action="store_true",
        help="Skip video generation (audio only)",
    )
    args = parser.parse_args()

    asyncio.run(
        main(
            issue_date=args.date,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
            skip_youtube=args.skip_youtube,
            skip_video=args.skip_video,
        )
    )
