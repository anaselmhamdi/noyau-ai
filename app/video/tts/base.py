"""Base classes for TTS providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from app.schemas.video import VideoScript


@dataclass
class SubtitleSegment:
    """A subtitle segment with timing information."""

    text: str
    start_time: float  # seconds
    end_time: float  # seconds


@dataclass
class TTSResult:
    """Result of TTS synthesis including subtitles."""

    audio_path: Path
    duration: float
    subtitles: list[SubtitleSegment]


class TTSProvider(ABC):
    """Abstract base class for TTS providers."""

    @abstractmethod
    async def synthesize(self, text: str, output_path: Path) -> TTSResult | None:
        """
        Synthesize speech from text with subtitle timestamps.

        Args:
            text: Text to synthesize
            output_path: Path to save the audio file

        Returns:
            TTSResult with audio path, duration, and subtitles, or None if failed
        """
        pass

    # Branded intro/outro for NoyauNews
    BRAND_INTRO = "This is Noyau News."
    BRAND_OUTRO = "Follow Noyau News for daily tech updates."

    def format_script_for_narration(self, script: VideoScript) -> str:
        """
        Format a video script for natural narration.

        Adds branded intro/outro and pauses between sections.
        """
        parts = [
            self.BRAND_INTRO,
            "...",  # Pause after brand intro
            script.hook,
            "...",  # Pause after hook
            script.intro,
            "...",  # Pause after intro
            script.body,
            "...",  # Pause before CTA
            script.cta,
            "...",  # Pause before outro
            self.BRAND_OUTRO,
        ]
        return " ".join(parts)
