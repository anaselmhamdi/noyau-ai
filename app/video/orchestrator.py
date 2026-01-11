"""Video generation orchestrator - coordinates the full pipeline."""

import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from loguru import Logger

from app.config import get_config
from app.core.logging import get_logger
from app.models.video import Video, VideoStatus
from app.pipeline.topics import detect_topic_from_identity
from app.schemas.llm import ClusterDistillOutput
from app.schemas.video import VideoClip, VideoGenerationResult, VideoScript
from app.services.storage_service import get_storage_service
from app.video.background_music import fetch_background_music
from app.video.compositor import compose_video
from app.video.script_generator import generate_script
from app.video.stock_footage import fetch_clips_for_script
from app.video.tts import SubtitleSegment, TTSResult, generate_srt, synthesize_script
from app.video.uploader import YouTubeUploader, create_video_metadata

logger = get_logger(__name__)


@dataclass
class VideoFormatConfig:
    """Video format settings for composition."""

    width: int = 1080
    height: int = 1920
    fps: int = 30
    duration_target: int = 45
    max_duration: int = 60


@dataclass
class VideoStyleConfig:
    """Visual style settings."""

    font: str = ""  # Will be set in __post_init__
    font_size: int = 48
    font_color: str = "#FFFFFF"
    background_color: str = "#0A0A0A"
    accent_color: str = "#FF6B35"

    def __post_init__(self) -> None:
        if not self.font:
            from app.video.config import get_default_font

            self.font = get_default_font()


@dataclass
class YouTubeConfigLocal:
    """YouTube upload settings."""

    category_id: str = "28"
    privacy_status: str = "public"
    made_for_kids: bool = False
    default_language: str = "en"
    default_tags: list[str] = field(default_factory=lambda: ["tech news", "programming", "noyau"])


@dataclass
class VideoConfigLocal:
    """Local video configuration for composition."""

    enabled: bool = False
    count: int = 3
    output_dir: str = "./output/videos"
    format: VideoFormatConfig = field(default_factory=VideoFormatConfig)
    style: VideoStyleConfig = field(default_factory=VideoStyleConfig)
    youtube: YouTubeConfigLocal = field(default_factory=YouTubeConfigLocal)


def get_video_config() -> VideoConfigLocal:
    """Get video configuration from config.yml."""
    config = get_config()
    video_cfg = config.video

    return VideoConfigLocal(
        enabled=video_cfg.enabled,
        count=video_cfg.count,
        output_dir=video_cfg.output_dir,
        format=VideoFormatConfig(
            width=video_cfg.format.width,
            height=video_cfg.format.height,
            fps=video_cfg.format.fps,
            duration_target=video_cfg.format.duration_target,
            max_duration=video_cfg.format.max_duration,
        ),
        style=VideoStyleConfig(
            font=video_cfg.style.font,
            font_size=video_cfg.style.font_size,
            font_color=video_cfg.style.font_color,
            background_color=video_cfg.style.background_color,
            accent_color=video_cfg.style.accent_color,
        ),
        youtube=YouTubeConfigLocal(
            category_id=video_cfg.youtube.category_id,
            privacy_status=video_cfg.youtube.privacy_status,
            made_for_kids=video_cfg.youtube.made_for_kids,
            default_language=video_cfg.youtube.default_language,
            default_tags=video_cfg.youtube.default_tags,
        ),
    )


# -----------------------------------------------------------------------------
# Status Update Helper
# -----------------------------------------------------------------------------


async def _update_video_status(
    db: AsyncSession | None,
    video_record: Video | None,
    status: VideoStatus,
    error_message: str | None = None,
    **kwargs: Any,
) -> None:
    """
    Centralized helper to update video record status.

    Args:
        db: Database session
        video_record: Video record to update
        status: New status to set
        error_message: Optional error message for failed status
        **kwargs: Additional fields to update on the video record
    """
    if not db or not video_record:
        return

    video_record.status = status
    if error_message:
        video_record.error_message = error_message

    for key, value in kwargs.items():
        if hasattr(video_record, key):
            setattr(video_record, key, value)

    await db.commit()


# -----------------------------------------------------------------------------
# Step Functions
# -----------------------------------------------------------------------------


async def _step_generate_script(
    summary: ClusterDistillOutput,
    topic: str,
    rank: int,
    log: "Logger",
) -> VideoScript | None:
    """
    Generate video script via LLM.

    Args:
        summary: Distilled cluster summary
        topic: Topic category
        rank: Rank in daily digest
        log: Bound logger instance

    Returns:
        VideoScript if successful, None otherwise
    """
    log.info("generating_video_script")
    script_result = await generate_script(summary, topic, rank)

    if not script_result:
        log.warning("script_generation_failed")
        return None

    return script_result.script


async def _step_synthesize_audio(
    script: VideoScript,
    video_dir: Path,
    provider: str,
    log: "Logger",
) -> TTSResult | None:
    """
    Synthesize TTS audio from script.

    Args:
        script: Video script to narrate
        video_dir: Directory for output files
        provider: TTS provider name (e.g., "edge")
        log: Bound logger instance

    Returns:
        TTSResult with audio path, duration, subtitles if successful, None otherwise
    """
    log.info("synthesizing_audio")
    audio_path = video_dir / "narration.mp3"
    tts_result = await synthesize_script(script, audio_path, provider=provider)

    if not tts_result:
        log.warning("audio_synthesis_failed")
        return None

    # Save SRT file for reference
    srt_path = video_dir / "subtitles.srt"
    generate_srt(tts_result.subtitles, srt_path)
    log.bind(subtitle_count=len(tts_result.subtitles)).debug("subtitles_generated")

    return tts_result


async def _step_fetch_footage(
    script: VideoScript,
    duration: float,
    video_dir: Path,
    log: "Logger",
) -> list[VideoClip]:
    """
    Fetch B-roll clips for the video.

    Args:
        script: Video script with visual keywords
        duration: Total duration needed
        video_dir: Directory for output files
        log: Bound logger instance

    Returns:
        List of VideoClip objects
    """
    log.info("fetching_stock_footage")
    clips_dir = video_dir / "clips"
    return await fetch_clips_for_script(
        keywords=script.visual_keywords,
        duration_needed=duration,
        output_dir=clips_dir,
    )


async def _step_fetch_music(
    topic: str,
    duration: float,
    video_dir: Path,
    log: "Logger",
) -> Path | None:
    """
    Fetch background music for the video.

    Args:
        topic: Topic category for music selection
        duration: Total duration needed
        video_dir: Directory for output files
        log: Bound logger instance

    Returns:
        Path to background music file if available, None otherwise
    """
    log.info("fetching_background_music")
    background_music_path = await fetch_background_music(
        topic=topic,
        duration_needed=duration,
        output_dir=video_dir,
    )
    if background_music_path:
        log.debug("background_music_available")
    return background_music_path


def _step_compose(
    script: VideoScript,
    audio_path: Path,
    clips: list[VideoClip],
    output_path: Path,
    config: VideoConfigLocal,
    subtitles: list[SubtitleSegment],
    background_music_path: Path | None,
    log: "Logger",
) -> VideoGenerationResult | None:
    """
    Compose the final video from all components.

    Args:
        script: Video script
        audio_path: Path to narration audio
        clips: List of B-roll clips
        output_path: Path for output video file
        config: Video configuration
        subtitles: List of subtitle segments
        background_music_path: Optional path to background music
        log: Bound logger instance

    Returns:
        VideoGenerationResult if successful, None otherwise
    """
    log.info("composing_video")
    result = compose_video(
        script=script,
        audio_path=audio_path,
        clips=clips,
        output_path=output_path,
        config=config,
        subtitles=subtitles,
        background_music_path=background_music_path,
    )

    if not result:
        log.warning("video_composition_failed")
        return None

    return result


async def _step_upload_s3(
    video_path: Path,
    issue_date: date,
    rank: int,
    log: "Logger",
) -> str | None:
    """
    Upload video to S3 for persistent storage.

    Args:
        video_path: Path to video file
        issue_date: Date of the issue
        rank: Rank in daily digest
        log: Bound logger instance

    Returns:
        S3 URL if successful, None otherwise
    """
    storage = get_storage_service()
    if not storage.is_configured():
        return None

    log.info("uploading_to_s3")
    s3_url = await storage.upload_video(
        video_path=video_path,
        issue_date=issue_date.isoformat(),
        rank=rank,
    )

    if s3_url:
        log.bind(s3_url=s3_url).info("video_uploaded_to_s3")

    return s3_url


async def _step_upload_youtube(
    video_path: Path,
    summary: ClusterDistillOutput,
    topic: str,
    rank: int,
    config: YouTubeConfigLocal,
    log: "Logger",
) -> tuple[str, str] | None:
    """
    Upload video to YouTube.

    Args:
        video_path: Path to video file
        summary: Distilled cluster summary for metadata
        topic: Topic category
        rank: Rank in daily digest
        config: YouTube configuration
        log: Bound logger instance

    Returns:
        Tuple of (video_id, video_url) if successful, None otherwise
    """
    log.info("uploading_to_youtube")

    uploader = YouTubeUploader(config=config)
    metadata = create_video_metadata(
        headline=summary.headline,
        teaser=summary.teaser,
        topic=topic,
        rank=rank,
        citations=[c.model_dump() for c in summary.citations],
        config=config,
    )

    upload_result = await uploader.upload_video(video_path, metadata)

    if upload_result:
        video_id, video_url = upload_result
        log.bind(youtube_url=video_url).info("video_published_to_youtube")
        return video_id, video_url

    log.warning("youtube_upload_failed_video_saved_locally")
    return None


# -----------------------------------------------------------------------------
# Main Orchestrator
# -----------------------------------------------------------------------------


async def generate_single_video(
    summary: ClusterDistillOutput,
    topic: str,
    rank: int,
    issue_date: date,
    cluster_id: str,
    output_dir: Path,
    config: VideoConfigLocal,
    db: AsyncSession | None = None,
    dry_run: bool = False,
) -> VideoGenerationResult | None:
    """
    Generate a single video from a cluster summary.

    Args:
        summary: Distilled cluster summary
        topic: Topic category
        rank: Rank in daily digest (1-3)
        issue_date: Date of the issue
        cluster_id: UUID of the cluster
        output_dir: Directory for output files
        config: Video configuration
        db: Optional database session for tracking
        dry_run: If True, skip actual generation

    Returns:
        VideoGenerationResult, or None if generation failed
    """
    video_dir = output_dir / issue_date.isoformat() / f"rank_{rank}"
    video_dir.mkdir(parents=True, exist_ok=True)

    log = logger.bind(rank=rank, headline=summary.headline[:50])

    # Track video in database if session provided
    video_record = None
    if db and not dry_run:
        video_record = Video(
            cluster_id=cluster_id,
            issue_date=issue_date,
            rank=rank,
            status=VideoStatus.GENERATING,
        )
        db.add(video_record)
        await db.commit()

    try:
        # Step 1: Generate script
        script = await _step_generate_script(summary, topic, rank, log)
        if not script:
            await _update_video_status(
                db, video_record, VideoStatus.FAILED, "Script generation failed"
            )
            return None

        if dry_run:
            log.info("dry_run_script_generated")
            return VideoGenerationResult(
                video_path="<dry-run>",
                duration_seconds=45.0,
                script=script,
            )

        # Store script in record
        await _update_video_status(
            db, video_record, VideoStatus.GENERATING, script_json=script.model_dump()
        )

        # Step 2: Synthesize audio
        tts_result = await _step_synthesize_audio(script, video_dir, provider="edge", log=log)
        if not tts_result:
            await _update_video_status(
                db, video_record, VideoStatus.FAILED, "Audio synthesis failed"
            )
            return None

        await _update_video_status(
            db,
            video_record,
            VideoStatus.GENERATING,
            audio_path=str(tts_result.audio_path),
            duration_seconds=tts_result.duration,
        )

        # Step 3: Fetch stock footage
        clips = await _step_fetch_footage(script, tts_result.duration, video_dir, log)

        # Step 3.5: Fetch background music
        background_music_path = await _step_fetch_music(topic, tts_result.duration, video_dir, log)

        # Step 4: Compose video
        video_path = video_dir / f"noyau_{rank}.mp4"
        result = _step_compose(
            script=script,
            audio_path=tts_result.audio_path,
            clips=clips,
            output_path=video_path,
            config=config,
            subtitles=tts_result.subtitles,
            background_music_path=background_music_path,
            log=log,
        )
        if not result:
            await _update_video_status(
                db, video_record, VideoStatus.FAILED, "Video composition failed"
            )
            return None

        await _update_video_status(
            db, video_record, VideoStatus.GENERATING, video_path=str(video_path)
        )

        # Step 5: Upload to S3
        s3_url = await _step_upload_s3(video_path, issue_date, rank, log)
        if s3_url:
            result.s3_url = s3_url
            await _update_video_status(db, video_record, VideoStatus.GENERATING, s3_url=s3_url)

        # Step 6: Upload to YouTube
        await _update_video_status(db, video_record, VideoStatus.UPLOADING)

        youtube_result = await _step_upload_youtube(
            video_path, summary, topic, rank, config.youtube, log
        )

        if youtube_result:
            video_id, video_url = youtube_result
            result.youtube_video_id = video_id
            result.youtube_url = video_url
            await _update_video_status(
                db,
                video_record,
                VideoStatus.PUBLISHED,
                youtube_video_id=video_id,
                youtube_url=video_url,
            )
        else:
            await _update_video_status(
                db, video_record, VideoStatus.FAILED, "YouTube upload failed"
            )

        # Cleanup temporary clips
        clips_dir = video_dir / "clips"
        if clips_dir.exists():
            shutil.rmtree(clips_dir)

        return result

    except Exception as e:
        log.bind(error=str(e)).error("video_generation_error")
        await _update_video_status(db, video_record, VideoStatus.FAILED, str(e))
        return None


async def generate_videos_for_issue(
    issue_date: date,
    ranked_with_summaries: list[tuple],
    db: AsyncSession | None = None,
    dry_run: bool = False,
) -> list[VideoGenerationResult]:
    """
    Generate videos for the top stories in an issue.

    Args:
        issue_date: Date of the issue
        ranked_with_summaries: List of (identity, items, score_info, distill_result) tuples
        db: Optional database session for tracking
        dry_run: If True, skip actual generation

    Returns:
        List of VideoGenerationResult objects
    """
    config = get_video_config()

    if not config.enabled:
        logger.info("video_generation_disabled")
        return []

    output_dir = Path(config.output_dir)
    results = []

    # Take top N stories for video generation
    top_stories = ranked_with_summaries[: config.count]

    logger.bind(count=len(top_stories)).info("starting_video_generation")

    for rank, (identity, items, score_info, distill_result) in enumerate(top_stories, start=1):
        if not distill_result:
            logger.bind(rank=rank, identity=identity[:50]).warning(
                "skipping_video_no_distill_result"
            )
            continue

        summary = distill_result.output

        # Determine topic from score info
        topic = _determine_topic(identity, score_info)

        # Get cluster_id from items if available
        cluster_id = _get_cluster_id(items, identity)

        result = await generate_single_video(
            summary=summary,
            topic=topic,
            rank=rank,
            issue_date=issue_date,
            cluster_id=cluster_id,
            output_dir=output_dir,
            config=config,
            db=db,
            dry_run=dry_run,
        )

        if result:
            results.append(result)

    logger.bind(
        total=len(top_stories),
        successful=len(results),
    ).info("video_generation_complete")

    return results


def _determine_topic(identity: str, score_info: dict) -> str:
    """Determine topic category from identity and score info."""
    topic = detect_topic_from_identity(identity, score_info.get("is_viral", False))
    # Video module uses "general" instead of "sauce" or "dev"
    if topic in ("sauce", "dev"):
        return "general"
    return topic


def _get_cluster_id(items: list, identity: str) -> str:
    """Extract cluster_id from items or use identity as fallback."""
    if items and hasattr(items[0], "cluster_items") and items[0].cluster_items:
        return str(items[0].cluster_items[0].cluster_id)
    return str(identity)[:50]
