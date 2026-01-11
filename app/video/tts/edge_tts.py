"""Microsoft Edge TTS provider."""

from pathlib import Path

import edge_tts

from app.core.logging import get_logger
from app.video.tts.base import SubtitleSegment, TTSProvider, TTSResult

logger = get_logger(__name__)


class EdgeTTS(TTSProvider):
    """
    Microsoft Edge TTS provider.

    Free, high-quality text-to-speech with word-level timestamps.
    """

    # Words to group together for natural subtitle pacing
    # Reduced to 3 for better fit with large font on mobile screens
    WORDS_PER_SUBTITLE = 3

    def __init__(self, voice: str = "en-US-GuyNeural"):
        """
        Initialize Edge TTS provider.

        Args:
            voice: Voice to use. Options include:
                - en-US-GuyNeural (male, professional)
                - en-US-JennyNeural (female, professional)
                - en-US-AriaNeural (female, friendly)
                - en-GB-RyanNeural (male, British)
        """
        self.voice = voice

    async def synthesize(self, text: str, output_path: Path) -> TTSResult | None:
        """Synthesize speech using Edge TTS with word timestamps."""
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            communicate = edge_tts.Communicate(text, self.voice, boundary="WordBoundary")

            # Collect word boundaries for subtitles
            word_boundaries: list[dict] = []

            # Write audio and collect metadata
            with open(output_path, "wb") as audio_file:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_file.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        word_boundaries.append(
                            {
                                "text": chunk["text"],
                                "offset": chunk["offset"] / 10_000_000,  # Convert to seconds
                                "duration": chunk["duration"] / 10_000_000,
                            }
                        )

            # Get audio duration
            duration = await self._get_audio_duration(output_path)

            # Convert word boundaries to subtitle segments
            subtitles = self._create_subtitle_segments(word_boundaries)

            logger.bind(
                voice=self.voice,
                duration=duration,
                subtitle_count=len(subtitles),
                path=str(output_path),
            ).info("edge_tts_synthesized_with_subtitles")

            return TTSResult(
                audio_path=output_path,
                duration=duration,
                subtitles=subtitles,
            )

        except Exception as e:
            logger.bind(error=str(e)).error("edge_tts_synthesis_error")
            return None

    def _create_subtitle_segments(self, word_boundaries: list[dict]) -> list[SubtitleSegment]:
        """
        Group words into subtitle segments for readable display.

        Groups words together (default 4 words per subtitle) for natural reading.
        """
        if not word_boundaries:
            return []

        segments: list[SubtitleSegment] = []
        current_words: list[str] = []
        segment_start = 0.0

        for i, word in enumerate(word_boundaries):
            if not current_words:
                segment_start = word["offset"]

            current_words.append(word["text"])

            # Create segment when we hit the word limit or end of text
            is_last = i == len(word_boundaries) - 1
            is_sentence_end = word["text"].rstrip().endswith((".", "!", "?", "..."))

            if len(current_words) >= self.WORDS_PER_SUBTITLE or is_sentence_end or is_last:
                segment_end = word["offset"] + word["duration"]
                segments.append(
                    SubtitleSegment(
                        text=" ".join(current_words),
                        start_time=segment_start,
                        end_time=segment_end,
                    )
                )
                current_words = []

        return segments

    async def _get_audio_duration(self, path: Path) -> float:
        """Get duration of audio file using mutagen."""
        try:
            from mutagen.mp3 import MP3

            audio = MP3(str(path))
            return float(audio.info.length)
        except ImportError:
            # Fallback: estimate from file size (~16kbps for speech)
            file_size = path.stat().st_size
            return file_size / 16000 * 8
        except Exception:
            return 45.0  # Default estimate
