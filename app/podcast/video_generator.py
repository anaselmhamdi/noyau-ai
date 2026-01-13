"""Podcast video generation with waveform animation."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from moviepy import AudioFileClip, VideoClip
from PIL import Image, ImageDraw, ImageFont
from scipy.io import wavfile

from app.core.logging import get_logger
from app.video.config import get_default_font

logger = get_logger(__name__)

# Video format for YouTube (landscape)
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30

# Waveform settings
WAVEFORM_BARS = 48  # Number of bars in the visualizer
WAVEFORM_HEIGHT = 250  # Max height of bars in pixels
WAVEFORM_Y = 540  # Y position of waveform center (centered vertically)
WAVEFORM_COLOR = (0, 207, 207)  # Cyan/teal to match Noyau branding (#00CFCF)
WAVEFORM_BAR_WIDTH = 24
WAVEFORM_GAP = 10
WAVEFORM_DECAY = 0.85  # How quickly bars fall (0-1, higher = slower decay)
WAVEFORM_ATTACK = 0.7  # How quickly bars rise (0-1, higher = faster attack)

# Text overlay settings
TITLE_Y = 320  # "NOYAU DAILY" above waveform
EPISODE_Y = 720  # Episode info below waveform
FONT_COLOR = (80, 80, 80)  # Dark gray for light backgrounds
FONT_SIZE_TITLE = 64
FONT_SIZE_EPISODE = 42


@dataclass
class PodcastVideoResult:
    """Result of podcast video generation."""

    video_path: str
    duration_seconds: float


class WaveformAnimator:
    """Animates waveform bars with smooth attack/decay based on audio amplitude."""

    def __init__(self, num_bars: int, sample_rate: int, audio_data: np.ndarray):
        """
        Initialize the waveform animator.

        Args:
            num_bars: Number of bars to display
            sample_rate: Audio sample rate
            audio_data: Normalized audio amplitude data (0-1)
        """
        self.num_bars = num_bars
        self.sample_rate = sample_rate
        self.audio_data = audio_data
        self.duration = len(audio_data) / sample_rate

        # Current bar heights (for smooth animation)
        self.bar_heights = np.zeros(num_bars)

        # Pre-generate random offsets for each bar (creates variation)
        np.random.seed(42)  # Consistent across runs
        self.bar_offsets = np.random.uniform(0.8, 1.2, num_bars)
        self.bar_phases = np.random.uniform(0, 2 * np.pi, num_bars)

    def get_amplitude_at_time(self, t: float, window_ms: float = 50) -> float:
        """Get the RMS amplitude of audio at time t."""
        # Convert time to sample index
        center_sample = int(t * self.sample_rate)
        window_samples = int((window_ms / 1000) * self.sample_rate)

        start = max(0, center_sample - window_samples // 2)
        end = min(len(self.audio_data), center_sample + window_samples // 2)

        if start >= end:
            return 0.0

        # Calculate RMS amplitude
        segment = self.audio_data[start:end]
        rms = float(np.sqrt(np.mean(segment**2)))
        return min(1.0, rms * 2.5)  # Scale up for visibility

    def get_bar_heights(self, t: float) -> np.ndarray:
        """
        Get animated bar heights for the current time.

        Returns array of bar heights (0-1) with smooth animation.
        """
        # Get current audio amplitude
        amplitude = self.get_amplitude_at_time(t)

        # Generate target heights for each bar with variation
        targets = np.zeros(self.num_bars)
        for i in range(self.num_bars):
            # Create wave-like variation across bars
            wave = 0.3 * np.sin(t * 3 + self.bar_phases[i])
            variation = self.bar_offsets[i] + wave

            # Bars in the middle are taller
            center_boost = 1.0 - 0.4 * abs(i - self.num_bars / 2) / (self.num_bars / 2)

            targets[i] = amplitude * variation * center_boost

        # Apply attack/decay smoothing
        for i in range(self.num_bars):
            if targets[i] > self.bar_heights[i]:
                # Attack (rising)
                self.bar_heights[i] += (targets[i] - self.bar_heights[i]) * WAVEFORM_ATTACK
            else:
                # Decay (falling)
                self.bar_heights[i] *= WAVEFORM_DECAY
                # Add minimum threshold
                if self.bar_heights[i] < 0.05:
                    self.bar_heights[i] = 0.05 + 0.03 * np.sin(t * 2 + self.bar_phases[i])

        return np.clip(self.bar_heights, 0.05, 1.0)


def load_audio_data(audio_path: Path) -> tuple[int, np.ndarray]:
    """
    Load and normalize audio data from file.

    Returns:
        Tuple of (sample_rate, normalized_mono_data)
    """
    with TemporaryDirectory() as temp_dir:
        wav_path = Path(temp_dir) / "audio.wav"

        # Convert to WAV
        audio = AudioFileClip(str(audio_path))
        audio.write_audiofile(
            str(wav_path),
            fps=22050,
            nbytes=2,
            codec="pcm_s16le",
            logger=None,
        )
        audio.close()

        # Read WAV
        sample_rate, audio_data = wavfile.read(wav_path)

    # Convert to mono
    if len(audio_data.shape) > 1:
        audio_data = audio_data.mean(axis=1)

    # Normalize to 0-1
    audio_data = np.abs(audio_data.astype(np.float32))
    max_val = np.max(audio_data)
    if max_val > 0:
        audio_data = audio_data / max_val

    return sample_rate, audio_data


def create_waveform_frame(
    background: Image.Image,
    bar_heights: np.ndarray,
    font: ImageFont.FreeTypeFont,
    title: str,
    episode_text: str,
) -> Image.Image:
    """
    Create a single frame of the waveform animation.

    Args:
        background: Background image
        bar_heights: Array of bar heights (0-1) for each bar
        font: Font for text rendering
        title: Episode title
        episode_text: Episode number/date text

    Returns:
        PIL Image with waveform overlay
    """
    frame = background.copy()
    draw = ImageDraw.Draw(frame)

    num_bars = len(bar_heights)

    # Draw waveform bars
    bar_total_width = WAVEFORM_BAR_WIDTH + WAVEFORM_GAP
    waveform_total_width = bar_total_width * num_bars
    start_x = (VIDEO_WIDTH - waveform_total_width) // 2

    for i, height in enumerate(bar_heights):
        # Calculate bar height in pixels
        bar_height = max(8, int(height * WAVEFORM_HEIGHT))

        x = start_x + i * bar_total_width
        y_top = WAVEFORM_Y - bar_height // 2
        y_bottom = WAVEFORM_Y + bar_height // 2

        # Draw bar with rounded corners
        draw.rounded_rectangle(
            [x, y_top, x + WAVEFORM_BAR_WIDTH, y_bottom],
            radius=WAVEFORM_BAR_WIDTH // 2,
            fill=WAVEFORM_COLOR,
        )

    # Draw title text (centered)
    title_font = font.font_variant(size=FONT_SIZE_TITLE)
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_width = title_bbox[2] - title_bbox[0]
    title_x = (VIDEO_WIDTH - title_width) // 2
    draw.text((title_x, TITLE_Y), title, font=title_font, fill=FONT_COLOR)

    # Draw episode text (centered)
    episode_font = font.font_variant(size=FONT_SIZE_EPISODE)
    episode_bbox = draw.textbbox((0, 0), episode_text, font=episode_font)
    episode_width = episode_bbox[2] - episode_bbox[0]
    episode_x = (VIDEO_WIDTH - episode_width) // 2
    draw.text((episode_x, EPISODE_Y), episode_text, font=episode_font, fill=FONT_COLOR)

    return frame


def generate_podcast_video(
    audio_path: Path,
    output_path: Path,
    episode_number: int,
    issue_date: date,
    background_image_path: Path | None = None,
) -> PodcastVideoResult | None:
    """
    Generate a podcast video with waveform animation.

    Args:
        audio_path: Path to the podcast audio file
        output_path: Path to save the video
        episode_number: Episode number for display
        issue_date: Date of the episode
        background_image_path: Optional custom background image

    Returns:
        PodcastVideoResult with video path and duration
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Load audio to get duration
        audio = AudioFileClip(str(audio_path))
        duration = audio.duration

        logger.bind(duration=duration).info("podcast_video_starting")

        # Load audio data for waveform animation
        logger.info("podcast_video_loading_audio")
        sample_rate, audio_data = load_audio_data(audio_path)

        # Create waveform animator
        animator = WaveformAnimator(WAVEFORM_BARS, sample_rate, audio_data)

        # Prepare background
        if background_image_path and background_image_path.exists():
            background = Image.open(background_image_path).convert("RGB")
            background = background.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.Resampling.LANCZOS)
        else:
            # Create dark gradient background
            background = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), (10, 10, 10))
            draw = ImageDraw.Draw(background)
            # Add subtle gradient
            for y in range(VIDEO_HEIGHT):
                brightness = int(10 + (y / VIDEO_HEIGHT) * 15)
                draw.line([(0, y), (VIDEO_WIDTH, y)], fill=(brightness, brightness, brightness))

        # Load font
        font_path = get_default_font()
        try:
            font = ImageFont.truetype(font_path, FONT_SIZE_TITLE)
        except Exception:
            font = ImageFont.load_default()

        # Prepare text
        title = "NOYAU DAILY"
        formatted_date = issue_date.strftime("%B %d, %Y")
        episode_text = f"Episode {episode_number} • {formatted_date}"

        # Create video frames using moviepy's make_frame
        def make_frame(t):
            # Get animated bar heights for current time
            bar_heights = animator.get_bar_heights(t)

            frame = create_waveform_frame(
                background,
                bar_heights,
                font,
                title,
                episode_text,
            )

            return np.array(frame)

        # Create video clip
        logger.info("podcast_video_rendering")
        video = VideoClip(make_frame, duration=duration)
        video = video.with_fps(VIDEO_FPS)

        # Add audio
        video = video.with_audio(audio)

        # Write video file
        video.write_videofile(
            str(output_path),
            fps=VIDEO_FPS,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            threads=4,
            logger=None,
        )

        # Cleanup
        video.close()
        audio.close()

        logger.bind(
            output=str(output_path),
            duration=duration,
        ).info("podcast_video_generated")

        return PodcastVideoResult(
            video_path=str(output_path),
            duration_seconds=duration,
        )

    except Exception as e:
        logger.bind(error=str(e)).error("podcast_video_generation_failed")
        import traceback

        traceback.print_exc()
        return None
