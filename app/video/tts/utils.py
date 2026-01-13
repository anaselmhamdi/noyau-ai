"""Utility functions for TTS module."""

from pathlib import Path

from app.schemas.video import CombinedVideoScript, VideoScript
from app.video.tts.base import SubtitleSegment, TTSProvider, TTSResult
from app.video.tts.edge_tts import EdgeTTS
from app.video.tts.elevenlabs_tts import ElevenLabsTTS
from app.video.tts.openai_tts import OpenAITTS


def get_tts_provider(provider: str = "edge") -> TTSProvider:
    """
    Get a TTS provider by name.

    Args:
        provider: Provider name ("edge", "openai", or "elevenlabs")

    Returns:
        TTSProvider instance
    """
    if provider == "openai":
        return OpenAITTS()
    if provider == "elevenlabs":
        return ElevenLabsTTS()
    return EdgeTTS()


async def synthesize_script(
    script: VideoScript,
    output_path: Path,
    provider: str = "edge",
) -> TTSResult | None:
    """
    Synthesize a video script to audio with subtitles.

    Args:
        script: Video script to synthesize
        output_path: Path to save the audio file
        provider: TTS provider name

    Returns:
        TTSResult with audio path, duration, and subtitles, or None if failed
    """
    tts = get_tts_provider(provider)
    text = tts.format_script_for_narration(script)
    return await tts.synthesize(text, output_path)


async def synthesize_combined_script(
    script: CombinedVideoScript,
    output_path: Path,
    provider: str = "edge",
) -> TTSResult | None:
    """
    Synthesize a combined video script to audio with subtitles.

    Args:
        script: Combined video script to synthesize
        output_path: Path to save the audio file
        provider: TTS provider name

    Returns:
        TTSResult with audio path, duration, and subtitles, or None if failed
    """
    tts = get_tts_provider(provider)
    text = tts.format_combined_script_for_narration(script)
    return await tts.synthesize(text, output_path)


def generate_srt(subtitles: list[SubtitleSegment], output_path: Path) -> None:
    """
    Generate an SRT subtitle file.

    Args:
        subtitles: List of subtitle segments
        output_path: Path to save the SRT file
    """
    with open(output_path, "w", encoding="utf-8") as f:
        for i, segment in enumerate(subtitles, 1):
            start = _format_srt_time(segment.start_time)
            end = _format_srt_time(segment.end_time)
            f.write(f"{i}\n")
            f.write(f"{start} --> {end}\n")
            f.write(f"{segment.text}\n\n")


def _format_srt_time(seconds: float) -> str:
    """Format seconds as SRT timestamp (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
