"""Video composition using MoviePy."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
)

from app.core.logging import get_logger
from app.schemas.video import (
    CombinedVideoGenerationResult,
    CombinedVideoScript,
    VideoClip,
    VideoGenerationResult,
    VideoScript,
)
from app.video.constants import (
    BRAND_FOLLOW_CTA,
    BRAND_INTRO_END,
    BRAND_NAME,
    COLOR_STROKE,
    COMBINED_BRAND_INTRO_END,
    COMBINED_CTA_DURATION,
    COMBINED_HOOK_END,
    COMBINED_INTRO_END,
    CTA_MAX_DURATION,
    FONT_SIZE_BRAND_INTRO,
    FONT_SIZE_HOOK,
    FONT_SIZE_OUTRO,
    FONT_SIZE_STORY_HEADLINE,
    FONT_SIZE_STORY_NUMBER,
    FONT_SIZE_SUBTITLE,
    HOOK_END,
    INTRO_END,
    MIN_BODY_DURATION,
    OUTRO_BUFFER,
    POSITION_CENTER_Y,
    POSITION_CTA_Y,
    POSITION_STORY_HEADLINE_Y,
    POSITION_STORY_NUMBER_Y,
    POSITION_SUBTITLE_Y,
    STORY_HEADLINE_DURATION,
    STORY_TRANSITION_DURATION,
    STROKE_WIDTH_DEFAULT,
    STROKE_WIDTH_SUBTITLE,
    SUBTITLE_MARGIN,
    SUBTITLE_WIDTH_MARGIN,
    TEXT_WIDTH_MARGIN,
)
from app.video.tts import SubtitleSegment

logger = get_logger(__name__)


class FormatConfig(Protocol):
    """Protocol for video format configuration."""

    width: int
    height: int
    fps: int


class StyleConfig(Protocol):
    """Protocol for video style configuration."""

    font: str
    font_size: int
    font_color: str
    background_color: str


class VideoConfigProtocol(Protocol):
    """Protocol for video configuration."""

    format: FormatConfig
    style: StyleConfig


@dataclass
class Timeline:
    """Video timeline with calculated section boundaries."""

    brand_intro_end: float
    hook_end: float
    intro_end: float
    body_end: float
    total_duration: float


def create_text_clip(
    text: str,
    duration: float,
    style: StyleConfig,
    format_config: FormatConfig,
    position: str | tuple = "center",
    fontsize: int | None = None,
) -> TextClip:
    """
    Create a text overlay clip.

    Args:
        text: Text to display
        duration: Duration in seconds
        style: Visual style configuration
        format_config: Video format configuration
        position: Position on screen ("center", "top", "bottom", or tuple with relative values)
        fontsize: Optional override for font size

    Returns:
        TextClip with styling applied
    """
    text_clip = TextClip(
        text=text,
        font_size=fontsize or style.font_size,
        color=style.font_color,
        font=style.font,
        stroke_color=COLOR_STROKE,
        stroke_width=STROKE_WIDTH_DEFAULT,
        text_align="center",
        method="caption",
        size=(format_config.width - TEXT_WIDTH_MARGIN, None),
    )

    # Convert relative tuple positions to pixel-based centering
    # This ensures text is properly centered at the target Y position
    if isinstance(position, tuple) and len(position) == 2:
        x_pos, y_pos = position
        if isinstance(y_pos, float) and 0 < y_pos < 1:
            # Convert relative Y to pixel, centering text vertically
            target_y = int(format_config.height * y_pos - text_clip.h / 2)
            # Clamp to safe bounds (not too close to edges)
            min_y = int(format_config.height * 0.15)
            max_y = int(format_config.height * 0.75)
            target_y = max(min_y, min(target_y, max_y))
            position = (x_pos, target_y)

    return text_clip.with_position(position).with_duration(duration)


def create_background_clip(
    duration: float,
    format_config: FormatConfig,
    style: StyleConfig,
) -> ColorClip:
    """Create a solid color background clip."""
    return ColorClip(
        size=(format_config.width, format_config.height),
        color=tuple(int(style.background_color.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)),
        duration=duration,
    )


def apply_ken_burns_effect(
    clip: VideoFileClip,
    target_size: tuple[int, int],
    zoom_factor: float = 1.2,
) -> VideoFileClip:
    """
    Apply a subtle Ken Burns (zoom/pan) effect to a clip.

    Args:
        clip: Input video clip
        target_size: Target (width, height)
        zoom_factor: Amount to zoom during the clip

    Returns:
        Clip with Ken Burns effect applied
    """

    def make_frame_effect(get_frame):
        def new_frame(t):
            # Placeholder for Ken Burns zoom effect
            # TODO: Apply zoom_factor based on progress through clip duration
            _ = t / clip.duration if clip.duration > 0 else 0  # progress (unused)
            _ = zoom_factor  # Silence unused warning
            return get_frame(t)

        return new_frame

    # For now, just resize to fill the target
    # Scale to cover the entire frame
    width_ratio = target_size[0] / clip.w
    height_ratio = target_size[1] / clip.h
    scale_factor = max(width_ratio, height_ratio) * 1.1  # Slight overshoot for cropping

    return clip.resized(scale_factor).cropped(
        x_center=clip.w * scale_factor / 2,
        y_center=clip.h * scale_factor / 2,
        width=target_size[0],
        height=target_size[1],
    )


def prepare_b_roll_clips(
    clips: list[VideoClip],
    total_duration: float,
    format_config: FormatConfig,
) -> list[VideoFileClip]:
    """
    Prepare B-roll clips for composition.

    Args:
        clips: List of VideoClip objects with paths
        total_duration: Total duration needed
        format_config: Video format configuration

    Returns:
        List of processed VideoFileClip objects
    """
    if not clips:
        return []

    processed = []
    duration_per_clip = total_duration / len(clips)
    target_size = (format_config.width, format_config.height)

    for clip_info in clips:
        try:
            clip = VideoFileClip(clip_info.path)

            # Limit clip duration
            clip_duration = min(clip.duration, duration_per_clip)
            clip = clip.subclipped(0, clip_duration)

            # Apply Ken Burns effect and resize
            clip = apply_ken_burns_effect(clip, target_size)

            # Remove audio (we'll use TTS)
            clip = clip.without_audio()

            processed.append(clip)

        except Exception as e:
            logger.bind(path=clip_info.path, error=str(e)).warning("b_roll_clip_processing_error")
            continue

    return processed


def mix_audio_with_background(
    narration: AudioFileClip,
    background_music_path: Path | None,
    background_volume: float = 0.05,
) -> AudioFileClip | CompositeAudioClip:
    """
    Mix narration audio with background music.

    Args:
        narration: Main narration audio clip
        background_music_path: Path to background music file
        background_volume: Volume level for background (0.0-1.0)

    Returns:
        Mixed audio clip, or original narration if no background
    """
    if not background_music_path or not background_music_path.exists():
        return narration

    try:
        background = AudioFileClip(str(background_music_path))

        # Trim or loop background to match narration duration
        if background.duration < narration.duration:
            # Loop the background music
            loops_needed = int(narration.duration / background.duration) + 1
            from moviepy import concatenate_audioclips

            background = concatenate_audioclips([background] * loops_needed)

        background = background.subclipped(0, narration.duration)

        # Apply volume reduction to background
        background = background.with_volume_scaled(background_volume)

        # Mix the two audio tracks
        mixed = CompositeAudioClip([narration, background])

        logger.debug("audio_mixed_with_background")
        return mixed

    except Exception as e:
        logger.bind(error=str(e)).warning("background_music_mixing_failed")
        return narration


def create_subtitle_clips(
    subtitles: list[SubtitleSegment],
    style: StyleConfig,
    format_config: FormatConfig,
) -> list[TextClip]:
    """
    Create text clips for subtitles with proper timing.

    Args:
        subtitles: List of subtitle segments with timing
        style: Visual style configuration
        format_config: Video format configuration

    Returns:
        List of TextClip objects with timing applied
    """
    subtitle_clips = []
    target_y_ratio = POSITION_SUBTITLE_Y

    for segment in subtitles:
        # Skip pause markers
        if segment.text.strip() == "...":
            continue

        # Create subtitle clip with timing
        subtitle_text = segment.text.upper()
        text_clip = TextClip(
            text=subtitle_text,
            font_size=style.font_size + FONT_SIZE_SUBTITLE,
            color=style.font_color,
            font=style.font,
            stroke_color=COLOR_STROKE,
            stroke_width=STROKE_WIDTH_SUBTITLE,
            text_align="center",
            method="caption",
            size=(format_config.width - SUBTITLE_WIDTH_MARGIN, None),
            margin=SUBTITLE_MARGIN,
        )

        # Center the subtitle vertically at the target position
        # This prevents bottom clipping on multi-line text by growing equally up/down
        target_y = int(format_config.height * target_y_ratio - text_clip.h / 2)
        # Clamp to safe bounds to prevent edge clipping
        min_y = int(format_config.height * 0.15)
        max_y = int(format_config.height - text_clip.h - format_config.height * 0.15)
        target_y = max(min_y, min(target_y, max_y))

        clip = (
            text_clip.with_position(("center", target_y))
            .with_start(segment.start_time)
            .with_end(segment.end_time)
        )
        subtitle_clips.append(clip)

    return subtitle_clips


def _calculate_timeline(total_duration: float) -> Timeline:
    """
    Calculate timing for all video sections.

    Args:
        total_duration: Total video duration in seconds

    Returns:
        Timeline with section boundaries
    """
    body_end = max(INTRO_END + MIN_BODY_DURATION, total_duration - OUTRO_BUFFER)
    return Timeline(
        brand_intro_end=BRAND_INTRO_END,
        hook_end=HOOK_END,
        intro_end=INTRO_END,
        body_end=body_end,
        total_duration=total_duration,
    )


def _create_brand_intro_clip(
    style: StyleConfig,
    format_config: FormatConfig,
    timeline: Timeline,
) -> TextClip:
    """
    Create the brand intro text overlay.

    Args:
        style: Visual style configuration
        format_config: Video format configuration
        timeline: Video timeline

    Returns:
        TextClip for brand intro
    """
    return create_text_clip(
        BRAND_NAME,
        timeline.brand_intro_end,
        style,
        format_config,
        position=("center", POSITION_CENTER_Y),
        fontsize=style.font_size + FONT_SIZE_BRAND_INTRO,
    )


def _create_hook_clip(
    hook_text: str,
    style: StyleConfig,
    format_config: FormatConfig,
    timeline: Timeline,
) -> TextClip:
    """
    Create the hook text overlay.

    Args:
        hook_text: Hook text from script
        style: Visual style configuration
        format_config: Video format configuration
        timeline: Video timeline

    Returns:
        TextClip for hook with start time applied
    """
    return create_text_clip(
        hook_text,
        timeline.hook_end - timeline.brand_intro_end,
        style,
        format_config,
        position=("center", POSITION_CENTER_Y),
        fontsize=style.font_size + FONT_SIZE_HOOK,
    ).with_start(timeline.brand_intro_end)


def _create_cta_clips(
    cta_text: str,
    style: StyleConfig,
    format_config: FormatConfig,
    timeline: Timeline,
) -> list[TextClip]:
    """
    Create CTA and brand outro text overlays.

    Args:
        cta_text: CTA text from script
        style: Visual style configuration
        format_config: Video format configuration
        timeline: Video timeline

    Returns:
        List of TextClips for CTA section (may be empty if no time available)
    """
    clips: list[TextClip] = []

    if timeline.total_duration <= timeline.body_end:
        return clips

    # CTA text
    cta_duration = min(CTA_MAX_DURATION, timeline.total_duration - timeline.body_end)
    cta_clip = create_text_clip(
        cta_text,
        cta_duration,
        style,
        format_config,
        position=("center", POSITION_CTA_Y),
        fontsize=style.font_size,
    ).with_start(timeline.body_end)
    clips.append(cta_clip)

    # Brand outro - "FOLLOW @NOYAUNEWS"
    outro_start = timeline.body_end + cta_duration
    if outro_start < timeline.total_duration:
        outro_clip = create_text_clip(
            BRAND_FOLLOW_CTA,
            timeline.total_duration - outro_start,
            style,
            format_config,
            position=("center", POSITION_CENTER_Y),
            fontsize=style.font_size + FONT_SIZE_OUTRO,
        ).with_start(outro_start)
        clips.append(outro_clip)

    return clips


def _filter_subtitle_clips(
    subtitle_clips: list[TextClip],
    timeline: Timeline,
) -> list[TextClip]:
    """
    Filter out subtitles that overlap with hook or CTA sections.

    Subtitles during hook time (0-5s) are hidden to avoid overlap with
    brand intro and hook text overlays. Audio continues playing normally.

    Args:
        subtitle_clips: List of subtitle clips
        timeline: Video timeline

    Returns:
        Filtered list of subtitle clips
    """
    filtered = []
    for clip in subtitle_clips:
        # Skip subtitles during hook time (brand intro + hook)
        if clip.start < timeline.hook_end:
            continue
        # Skip subtitles during CTA time
        if clip.start >= timeline.body_end:
            continue
        filtered.append(clip)
    return filtered


def _prepare_background(
    b_roll_clips: list[VideoFileClip],
    total_duration: float,
    format_config: FormatConfig,
    style: StyleConfig,
) -> ColorClip | VideoFileClip:
    """
    Prepare video background from B-roll or solid color.

    Args:
        b_roll_clips: Processed B-roll clips
        total_duration: Total video duration
        format_config: Video format configuration
        style: Visual style configuration

    Returns:
        Background clip (B-roll sequence or solid color)
    """
    if not b_roll_clips:
        return create_background_clip(total_duration, format_config, style)

    b_roll_sequence = concatenate_videoclips(b_roll_clips, method="compose")

    # Loop if needed to fill total duration
    if b_roll_sequence.duration < total_duration:
        loops_needed = int(total_duration / b_roll_sequence.duration) + 1
        b_roll_clips_extended = b_roll_clips * loops_needed
        b_roll_sequence = concatenate_videoclips(
            b_roll_clips_extended, method="compose"
        ).subclipped(0, total_duration)

    return b_roll_sequence.subclipped(0, total_duration)


def compose_video(
    script: VideoScript,
    audio_path: Path,
    clips: list[VideoClip],
    output_path: Path,
    config: VideoConfigProtocol | None = None,
    subtitles: list[SubtitleSegment] | None = None,
    background_music_path: Path | None = None,
) -> VideoGenerationResult | None:
    """
    Compose a complete video from script, audio, and B-roll.

    Args:
        script: Video script with sections
        audio_path: Path to narration audio
        clips: List of B-roll clips
        output_path: Path to save the final video
        config: Video configuration
        subtitles: Optional list of subtitle segments with timing
        background_music_path: Optional path to background music file

    Returns:
        VideoGenerationResult, or None if composition failed
    """
    actual_config: VideoConfigProtocol
    if config is None:
        from app.video.config import VideoConfig as DefaultConfig

        actual_config = DefaultConfig()  # type: ignore[assignment]
    else:
        actual_config = config
    format_config = actual_config.format
    style = actual_config.style

    try:
        # Load audio and calculate timeline
        audio = AudioFileClip(str(audio_path))
        timeline = _calculate_timeline(audio.duration)

        # Prepare background
        b_roll_clips = prepare_b_roll_clips(clips, timeline.total_duration, format_config)
        background = _prepare_background(
            b_roll_clips, timeline.total_duration, format_config, style
        )

        # Create text overlays
        text_clips = [
            _create_brand_intro_clip(style, format_config, timeline),
            _create_hook_clip(script.hook, style, format_config, timeline),
        ]
        text_clips.extend(_create_cta_clips(script.cta, style, format_config, timeline))

        # Create and filter subtitle clips
        subtitle_clips = []
        if subtitles:
            subtitle_clips = create_subtitle_clips(subtitles, style, format_config)
            subtitle_clips = _filter_subtitle_clips(subtitle_clips, timeline)
            logger.bind(subtitle_count=len(subtitle_clips)).info("subtitle_clips_created")
        else:
            logger.warning("no_subtitles_provided")

        # Compose all layers
        final_video = CompositeVideoClip(
            [background] + text_clips + subtitle_clips,
            size=(format_config.width, format_config.height),
        )

        # Mix audio with background music and attach
        mixed_audio = mix_audio_with_background(audio, background_music_path)
        final_video = final_video.with_audio(mixed_audio)

        # Write output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        final_video.write_videofile(
            str(output_path),
            fps=format_config.fps,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            threads=4,
            logger=None,
        )

        # Clean up resources
        audio.close()
        final_video.close()
        for clip in b_roll_clips:
            clip.close()

        logger.bind(
            output=str(output_path),
            duration=timeline.total_duration,
        ).info("video_composed_successfully")

        return VideoGenerationResult(
            video_path=str(output_path),
            duration_seconds=timeline.total_duration,
            script=script,
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        logger.bind(error=str(e)).error("video_composition_error")
        return None


# -----------------------------------------------------------------------------
# Combined Multi-Story Video Composition
# -----------------------------------------------------------------------------


@dataclass
class CombinedTimeline:
    """Video timeline for combined 3-story video."""

    brand_intro_end: float
    hook_end: float
    intro_end: float
    story_segments: list[tuple[float, float]]  # (start, end) for each story
    cta_start: float
    total_duration: float


def _calculate_combined_timeline(total_duration: float) -> CombinedTimeline:
    """
    Calculate timing for combined video sections.

    Timeline structure (~60s):
    - 0-2s: Brand intro
    - 2-5s: Hook
    - 5-10s: Intro
    - 10-28s: Story 1 (transition + body)
    - 28-46s: Story 2 (transition + body)
    - 46-55s: Story 3 (transition + body)
    - 55-end: CTA + outro
    """
    # Calculate story segment duration
    stories_start = COMBINED_INTRO_END
    cta_start = total_duration - COMBINED_CTA_DURATION
    stories_duration = cta_start - stories_start
    story_duration = stories_duration / 3

    story_segments = []
    current_time = stories_start
    for _ in range(3):
        story_segments.append((current_time, current_time + story_duration))
        current_time += story_duration

    return CombinedTimeline(
        brand_intro_end=COMBINED_BRAND_INTRO_END,
        hook_end=COMBINED_HOOK_END,
        intro_end=COMBINED_INTRO_END,
        story_segments=story_segments,
        cta_start=cta_start,
        total_duration=total_duration,
    )


def _create_story_transition_clips(
    script: CombinedVideoScript,
    style: StyleConfig,
    format_config: FormatConfig,
    timeline: CombinedTimeline,
) -> list[TextClip]:
    """
    Create numbered transition overlays for each story.

    Shows "1", "2", "3" indicators and headline text during transitions.
    """
    clips = []

    for i, (story, (start, _end)) in enumerate(
        zip(script.stories, timeline.story_segments), start=1
    ):
        # Large story number indicator
        number_clip = create_text_clip(
            str(i),
            STORY_TRANSITION_DURATION,
            style,
            format_config,
            position=("center", POSITION_STORY_NUMBER_Y),
            fontsize=FONT_SIZE_STORY_NUMBER,
        ).with_start(start)
        clips.append(number_clip)

        # Headline overlay below number
        headline_clip = create_text_clip(
            story.headline_text.upper(),
            STORY_HEADLINE_DURATION,
            style,
            format_config,
            position=("center", POSITION_STORY_HEADLINE_Y),
            fontsize=FONT_SIZE_STORY_HEADLINE,
        ).with_start(start)
        clips.append(headline_clip)

    return clips


def _filter_combined_subtitle_clips(
    subtitle_clips: list[TextClip],
    timeline: CombinedTimeline,
) -> list[TextClip]:
    """
    Filter out subtitles that overlap with hook, transitions, or CTA sections.

    Args:
        subtitle_clips: List of subtitle clips
        timeline: Combined video timeline

    Returns:
        Filtered list of subtitle clips
    """
    filtered = []
    for clip in subtitle_clips:
        # Skip subtitles during hook time (brand intro + hook)
        if clip.start < timeline.hook_end:
            continue
        # Skip subtitles during CTA time
        if clip.start >= timeline.cta_start:
            continue
        # Skip subtitles during story transitions (first 3 seconds of each story)
        skip = False
        for story_start, _story_end in timeline.story_segments:
            if story_start <= clip.start < story_start + STORY_HEADLINE_DURATION:
                skip = True
                break
        if skip:
            continue
        filtered.append(clip)
    return filtered


def compose_combined_video(
    script: CombinedVideoScript,
    audio_path: Path,
    clips: list[VideoClip],
    output_path: Path,
    config: VideoConfigProtocol | None = None,
    subtitles: list[SubtitleSegment] | None = None,
    background_music_path: Path | None = None,
) -> CombinedVideoGenerationResult | None:
    """
    Compose a combined 3-story video.

    Similar to compose_video but with:
    - Story number transitions ("1", "2", "3")
    - Headline overlays during transitions
    - Visual dividers between stories

    Args:
        script: Combined video script with 3 stories
        audio_path: Path to narration audio
        clips: List of B-roll clips
        output_path: Path to save the final video
        config: Video configuration
        subtitles: Optional list of subtitle segments with timing
        background_music_path: Optional path to background music file

    Returns:
        CombinedVideoGenerationResult, or None if composition failed
    """
    actual_config: VideoConfigProtocol
    if config is None:
        from app.video.config import VideoConfig as DefaultConfig

        actual_config = DefaultConfig()  # type: ignore[assignment]
    else:
        actual_config = config
    format_config = actual_config.format
    style = actual_config.style

    try:
        # Load audio and calculate timeline
        audio = AudioFileClip(str(audio_path))
        timeline = _calculate_combined_timeline(audio.duration)

        # Prepare background
        b_roll_clips = prepare_b_roll_clips(clips, timeline.total_duration, format_config)
        background = _prepare_background(
            b_roll_clips, timeline.total_duration, format_config, style
        )

        # Create text overlays
        text_clips = [
            # Brand intro
            create_text_clip(
                BRAND_NAME,
                timeline.brand_intro_end,
                style,
                format_config,
                position=("center", POSITION_CENTER_Y),
                fontsize=style.font_size + FONT_SIZE_BRAND_INTRO,
            ),
            # Hook
            create_text_clip(
                script.hook,
                timeline.hook_end - timeline.brand_intro_end,
                style,
                format_config,
                position=("center", POSITION_CENTER_Y),
                fontsize=style.font_size + FONT_SIZE_HOOK,
            ).with_start(timeline.brand_intro_end),
        ]

        # Add story transition clips (numbers and headlines)
        text_clips.extend(_create_story_transition_clips(script, style, format_config, timeline))

        # Add CTA and outro
        cta_clip = create_text_clip(
            script.cta,
            min(CTA_MAX_DURATION, timeline.total_duration - timeline.cta_start),
            style,
            format_config,
            position=("center", POSITION_CTA_Y),
            fontsize=style.font_size,
        ).with_start(timeline.cta_start)
        text_clips.append(cta_clip)

        # Brand outro
        outro_start = timeline.cta_start + CTA_MAX_DURATION
        if outro_start < timeline.total_duration:
            outro_clip = create_text_clip(
                BRAND_FOLLOW_CTA,
                timeline.total_duration - outro_start,
                style,
                format_config,
                position=("center", POSITION_CENTER_Y),
                fontsize=style.font_size + FONT_SIZE_OUTRO,
            ).with_start(outro_start)
            text_clips.append(outro_clip)

        # Create and filter subtitle clips
        subtitle_clips = []
        if subtitles:
            subtitle_clips = create_subtitle_clips(subtitles, style, format_config)
            subtitle_clips = _filter_combined_subtitle_clips(subtitle_clips, timeline)
            logger.bind(subtitle_count=len(subtitle_clips)).info("combined_subtitle_clips_created")
        else:
            logger.warning("no_subtitles_provided_for_combined")

        # Compose all layers
        final_video = CompositeVideoClip(
            [background] + text_clips + subtitle_clips,
            size=(format_config.width, format_config.height),
        )

        # Mix audio with background music and attach
        mixed_audio = mix_audio_with_background(audio, background_music_path)
        final_video = final_video.with_audio(mixed_audio)

        # Write output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        final_video.write_videofile(
            str(output_path),
            fps=format_config.fps,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            threads=4,
            logger=None,
        )

        # Clean up resources
        audio.close()
        final_video.close()
        for clip in b_roll_clips:
            clip.close()

        logger.bind(
            output=str(output_path),
            duration=timeline.total_duration,
        ).info("combined_video_composed_successfully")

        return CombinedVideoGenerationResult(
            video_path=str(output_path),
            duration_seconds=timeline.total_duration,
            script=script,
            story_headlines=[s.headline_text for s in script.stories],
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        logger.bind(error=str(e)).error("combined_video_composition_error")
        return None
