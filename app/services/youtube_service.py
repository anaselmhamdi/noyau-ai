"""
YouTube service for dispatching videos to YouTube.

Handles uploading shorts (daily digest videos) and podcast episodes to YouTube.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.core.logging import get_logger
from app.models.issue import Issue
from app.schemas.llm import ClusterDistillOutput
from app.schemas.video import VideoGenerationResult, YouTubeMetadata
from app.video.orchestrator import get_video_config
from app.video.uploader import YouTubeUploader, create_video_metadata

logger = get_logger(__name__)


@dataclass
class YouTubeUploadResult:
    """Result of uploading to YouTube."""

    success: bool
    video_id: str | None = None
    video_url: str | None = None
    error: str | None = None


@dataclass
class YouTubeShortsResult:
    """Result of uploading shorts to YouTube."""

    results: list[YouTubeUploadResult]
    success: bool
    uploaded_count: int
    message: str


@dataclass
class YouTubePodcastResult:
    """Result of uploading podcast to YouTube."""

    success: bool
    message: str
    video_id: str | None = None
    video_url: str | None = None


async def send_youtube_shorts(
    issue_date: date,
    video_results: list[VideoGenerationResult],
    summaries: list[ClusterDistillOutput],
    topics: list[str],
) -> YouTubeShortsResult:
    """
    Upload short-form videos to YouTube.

    Args:
        issue_date: Date of the issue
        video_results: List of generated video results with S3 URLs
        summaries: List of cluster summaries for metadata
        topics: List of topic categories

    Returns:
        YouTubeShortsResult with upload status
    """
    config = get_video_config()
    uploader = YouTubeUploader(config=config.youtube)

    results: list[YouTubeUploadResult] = []
    uploaded_count = 0

    for i, video in enumerate(video_results):
        if not video.s3_url:
            logger.bind(rank=i + 1).warning("video_has_no_s3_url_skipping_youtube")
            results.append(YouTubeUploadResult(success=False, error="No S3 URL"))
            continue

        # Skip if already uploaded to YouTube
        if video.youtube_video_id:
            logger.bind(rank=i + 1, youtube_id=video.youtube_video_id).info(
                "video_already_on_youtube"
            )
            results.append(
                YouTubeUploadResult(
                    success=True,
                    video_id=video.youtube_video_id,
                    video_url=video.youtube_url,
                )
            )
            uploaded_count += 1
            continue

        # Get corresponding summary and topic
        summary = summaries[i] if i < len(summaries) else None
        topic = topics[i] if i < len(topics) else "general"

        if not summary:
            logger.bind(rank=i + 1).warning("no_summary_for_video_skipping")
            results.append(YouTubeUploadResult(success=False, error="No summary"))
            continue

        try:
            # Download video from S3 to temp location
            video_path = await _download_from_s3(video.s3_url, issue_date, i + 1)
            if not video_path:
                results.append(YouTubeUploadResult(success=False, error="S3 download failed"))
                continue

            # Create metadata
            metadata = create_video_metadata(
                headline=summary.headline,
                teaser=summary.teaser,
                topic=topic,
                rank=i + 1,
                citations=[c.model_dump() for c in summary.citations],
                config=config.youtube,
            )

            # Upload to YouTube
            upload_result = await uploader.upload_video(video_path, metadata)

            if upload_result:
                video_id, video_url = upload_result
                logger.bind(rank=i + 1, youtube_url=video_url).info("short_uploaded_to_youtube")
                results.append(
                    YouTubeUploadResult(success=True, video_id=video_id, video_url=video_url)
                )
                uploaded_count += 1

                # Update video result with YouTube info
                video.youtube_video_id = video_id
                video.youtube_url = video_url

                # Cleanup temp file
                video_path.unlink(missing_ok=True)
            else:
                results.append(YouTubeUploadResult(success=False, error="Upload failed"))

        except Exception as e:
            logger.bind(rank=i + 1, error=str(e)).error("youtube_short_upload_error")
            results.append(YouTubeUploadResult(success=False, error=str(e)))

    success = uploaded_count > 0
    message = f"Uploaded {uploaded_count}/{len(video_results)} shorts to YouTube"

    return YouTubeShortsResult(
        results=results,
        success=success,
        uploaded_count=uploaded_count,
        message=message,
    )


async def send_youtube_podcast(
    issue_date: date,
    issue: Issue,
) -> YouTubePodcastResult:
    """
    Upload podcast episode to YouTube as audio with static video.

    Uses the podcast video (with waveform) generated by podcast_generate.py.

    Args:
        issue_date: Date of the issue
        issue: Issue record with podcast data

    Returns:
        YouTubePodcastResult with upload status
    """
    if not issue.podcast_audio_url:
        return YouTubePodcastResult(
            success=False,
            message="No podcast audio available",
        )

    # Check if already uploaded
    if issue.podcast_youtube_url:
        logger.info("podcast_already_on_youtube")
        return YouTubePodcastResult(
            success=True,
            video_url=issue.podcast_youtube_url,
            message="Podcast already on YouTube",
        )

    # Look for podcast video in S3
    # The podcast video is uploaded by podcast_generate.py to:
    # podcasts/{date}/noyau_daily.mp4
    from app.services.storage_service import get_storage_service

    storage = get_storage_service()
    if not storage.is_configured():
        return YouTubePodcastResult(
            success=False,
            message="S3 not configured",
        )

    video_key = f"podcasts/{issue_date.isoformat()}/noyau_daily.mp4"

    try:
        # Download podcast video from S3
        video_path = Path(f"/tmp/podcast_{issue_date.isoformat()}.mp4")
        downloaded = await storage.download_file(video_key, video_path)

        if not downloaded or not video_path.exists():
            return YouTubePodcastResult(
                success=False,
                message="Podcast video not found in S3",
            )

        # Create YouTube metadata for podcast
        config = get_video_config()
        uploader = YouTubeUploader(config=config.youtube)

        date_str = issue_date.strftime("%B %d, %Y")
        duration_min = int((issue.podcast_duration_seconds or 480) / 60)

        metadata = YouTubeMetadata(
            title=f"Noyau Daily Podcast - {date_str} | {duration_min} min Tech Briefing",
            description=f"""Your daily tech briefing for {date_str}.

Top 5 stories in {duration_min} minutes - perfect for your commute.

Subscribe for daily tech updates.

Website: https://noyau.news
Podcast: https://noyau.news/podcast
Twitter: https://twitter.com/NoyauNews
Discord: https://discord.gg/YCbuNqFucb

#technews #podcast #dailybriefing #noyau
""",
            tags=config.youtube.default_tags + ["podcast", "audio", "daily briefing"],
            category_id=config.youtube.category_id,
            privacy_status=config.youtube.privacy_status,
            made_for_kids=config.youtube.made_for_kids,
        )

        # Upload to YouTube
        upload_result = await uploader.upload_video(video_path, metadata)

        # Cleanup temp file
        video_path.unlink(missing_ok=True)

        if upload_result:
            video_id, video_url = upload_result
            logger.bind(youtube_url=video_url).info("podcast_uploaded_to_youtube")

            return YouTubePodcastResult(
                success=True,
                video_id=video_id,
                video_url=video_url,
                message=f"Podcast uploaded to YouTube: {video_url}",
            )
        else:
            return YouTubePodcastResult(
                success=False,
                message="YouTube upload failed",
            )

    except Exception as e:
        logger.bind(error=str(e)).error("youtube_podcast_upload_error")
        return YouTubePodcastResult(
            success=False,
            message=str(e),
        )


async def _download_from_s3(s3_url: str, issue_date: date, rank: int) -> Path | None:
    """Download video from S3 to temp location."""
    from app.services.storage_service import get_storage_service

    storage = get_storage_service()
    if not storage.is_configured():
        return None

    # Extract key from S3 URL
    # URL format: https://bucket.s3.region.amazonaws.com/key
    # or: https://s3.region.amazonaws.com/bucket/key
    try:
        from urllib.parse import urlparse

        parsed = urlparse(s3_url)
        key = parsed.path.lstrip("/")

        # If bucket is in hostname, path is the key directly
        # If bucket is in path, need to strip bucket name
        if storage.bucket_name and key.startswith(storage.bucket_name):
            key = key[len(storage.bucket_name) :].lstrip("/")

        video_path = Path(f"/tmp/video_{issue_date.isoformat()}_{rank}.mp4")
        downloaded = await storage.download_file(key, video_path)

        if downloaded and video_path.exists():
            return video_path
        return None

    except Exception as e:
        logger.bind(error=str(e)).error("s3_download_failed")
        return None
