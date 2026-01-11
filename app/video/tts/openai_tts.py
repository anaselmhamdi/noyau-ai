"""OpenAI TTS provider."""

from pathlib import Path

from openai import AsyncOpenAI

from app.config import get_settings
from app.core.logging import get_logger
from app.video.tts.base import SubtitleSegment, TTSProvider, TTSResult

logger = get_logger(__name__)


class OpenAITTS(TTSProvider):
    """
    OpenAI TTS provider.

    Higher quality but costs ~$15/1M characters.
    Note: OpenAI TTS doesn't provide word-level timestamps, so subtitles are estimated.
    """

    def __init__(
        self,
        voice: str = "nova",
        model: str = "tts-1",
        api_key: str | None = None,
    ):
        """
        Initialize OpenAI TTS provider.

        Args:
            voice: Voice to use. Options:
                - alloy, echo, fable, onyx, nova, shimmer
            model: Model to use (tts-1 or tts-1-hd)
            api_key: Optional API key (defaults to settings)
        """
        settings = get_settings()
        self.api_key = api_key or settings.openai_api_key
        self.voice = voice
        self.model = model

    async def synthesize(self, text: str, output_path: Path) -> TTSResult | None:
        """Synthesize speech using OpenAI TTS."""
        if not self.api_key:
            logger.warning("openai_api_key_not_set_for_tts")
            return None

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            client = AsyncOpenAI(api_key=self.api_key)
            response = await client.audio.speech.create(
                model=self.model,
                voice=self.voice,
                input=text,
            )

            # Write to file
            output_path.write_bytes(response.content)

            # Estimate duration from character count (~15 chars/second)
            duration = len(text) / 15.0

            # Generate estimated subtitles (OpenAI doesn't provide timestamps)
            subtitles = self._estimate_subtitles(text, duration)

            logger.bind(
                voice=self.voice,
                model=self.model,
                duration=duration,
                subtitle_count=len(subtitles),
                path=str(output_path),
            ).info("openai_tts_synthesized")

            return TTSResult(
                audio_path=output_path,
                duration=duration,
                subtitles=subtitles,
            )

        except Exception as e:
            logger.bind(error=str(e)).error("openai_tts_synthesis_error")
            return None

    def _estimate_subtitles(self, text: str, duration: float) -> list[SubtitleSegment]:
        """
        Estimate subtitle timing based on text length.

        Since OpenAI TTS doesn't provide word boundaries, we estimate based on
        character count and average speaking rate.
        """
        words = text.split()
        if not words:
            return []

        segments = []
        words_per_segment = 4
        chars_per_second = len(text) / duration if duration > 0 else 15

        current_char_pos = 0
        for i in range(0, len(words), words_per_segment):
            segment_words = words[i : i + words_per_segment]
            segment_text = " ".join(segment_words)

            start_time = current_char_pos / chars_per_second
            current_char_pos += len(segment_text) + 1  # +1 for space
            end_time = current_char_pos / chars_per_second

            segments.append(
                SubtitleSegment(
                    text=segment_text,
                    start_time=start_time,
                    end_time=min(end_time, duration),
                )
            )

        return segments
