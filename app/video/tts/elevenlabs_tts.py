"""ElevenLabs TTS provider."""

from pathlib import Path

from app.config import get_settings
from app.core.logging import get_logger
from app.video.tts.base import SubtitleSegment, TTSProvider, TTSResult

logger = get_logger(__name__)


class ElevenLabsTTS(TTSProvider):
    """
    ElevenLabs TTS provider.

    Best quality voices with word-level timestamps for accurate subtitles.
    Requires ELEVENLABS_API_KEY in environment.
    """

    # Words to group together for natural subtitle pacing
    WORDS_PER_SUBTITLE = 3

    def __init__(
        self,
        voice_id: str = "pNInz6obpgDQGcFmaJgB",  # "Adam" - clear male voice
        model_id: str = "eleven_multilingual_v2",
        api_key: str | None = None,
    ):
        """
        Initialize ElevenLabs TTS provider.

        Args:
            voice_id: Voice ID to use. Popular options:
                - pNInz6obpgDQGcFmaJgB (Adam - clear male)
                - EXAVITQu4vr4xnSDxMaL (Bella - female)
                - 21m00Tcm4TlvDq8ikWAM (Rachel - female)
                - AZnzlk1XvdvUeBnXmlld (Domi - female)
            model_id: Model to use (eleven_multilingual_v2 recommended)
            api_key: Optional API key override
        """
        self.voice_id = voice_id
        self.model_id = model_id
        settings = get_settings()
        self.api_key = api_key or getattr(settings, "elevenlabs_api_key", None)

    async def synthesize(self, text: str, output_path: Path) -> TTSResult | None:
        """Synthesize speech with ElevenLabs and get word-level timestamps."""
        if not self.api_key:
            logger.error("elevenlabs_api_key_not_set")
            return None

        try:
            import base64

            from elevenlabs import ElevenLabs

            client = ElevenLabs(api_key=self.api_key)

            # Generate speech with timestamps
            response = client.text_to_speech.convert_with_timestamps(
                voice_id=self.voice_id,
                text=text,
                model_id=self.model_id,
            )

            # Decode and save audio
            audio_data = base64.b64decode(response.audio_base_64)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(audio_data)

            # Extract word-level timestamps from character alignment
            subtitles = self._create_subtitle_segments(text, response.alignment)

            # Get duration from last character timestamp
            duration = 0.0
            if response.alignment and response.alignment.character_end_times_seconds:
                duration = response.alignment.character_end_times_seconds[-1]

            logger.bind(
                duration=duration,
                subtitle_count=len(subtitles),
            ).info("elevenlabs_synthesis_complete")

            return TTSResult(
                audio_path=output_path,
                duration=duration,
                subtitles=subtitles,
            )

        except Exception as e:
            logger.bind(error=str(e)).error("elevenlabs_synthesis_failed")
            return None

    def _create_subtitle_segments(self, text: str, alignment) -> list[SubtitleSegment]:
        """Create subtitle segments from ElevenLabs character-level alignment."""
        if not alignment or not alignment.characters:
            return []

        segments: list[SubtitleSegment] = []
        words: list[dict[str, str | float]] = []
        current_word = ""
        word_start = 0.0
        word_end = 0.0

        chars = alignment.characters
        starts = alignment.character_start_times_seconds
        ends = alignment.character_end_times_seconds

        # Build words from characters
        for i, char in enumerate(chars):
            if char == " " or char == "\n":
                if current_word:
                    words.append(
                        {
                            "text": current_word,
                            "start": word_start,
                            "end": word_end,
                        }
                    )
                    current_word = ""
            else:
                if not current_word:
                    word_start = float(starts[i]) if i < len(starts) else word_end
                current_word += char
                word_end = float(ends[i]) if i < len(ends) else word_end

        # Don't forget the last word
        if current_word:
            words.append(
                {
                    "text": current_word,
                    "start": word_start,
                    "end": word_end,
                }
            )

        # Group words into subtitle segments
        current_words: list[dict[str, str | float]] = []
        segment_start = 0.0

        for word in words:
            # Skip pause markers
            if word["text"] == "...":
                if current_words:
                    segments.append(
                        SubtitleSegment(
                            text=" ".join(str(w["text"]) for w in current_words),
                            start_time=segment_start,
                            end_time=float(current_words[-1]["end"]),
                        )
                    )
                    current_words = []
                continue

            if not current_words:
                segment_start = float(word["start"])

            current_words.append(word)

            # Create segment when we hit word limit or sentence end
            is_sentence_end = str(word["text"]).rstrip().endswith((".", "!", "?"))
            if len(current_words) >= self.WORDS_PER_SUBTITLE or is_sentence_end:
                segments.append(
                    SubtitleSegment(
                        text=" ".join(str(w["text"]) for w in current_words),
                        start_time=segment_start,
                        end_time=float(word["end"]),
                    )
                )
                current_words = []

        # Handle remaining words
        if current_words:
            segments.append(
                SubtitleSegment(
                    text=" ".join(str(w["text"]) for w in current_words),
                    start_time=segment_start,
                    end_time=float(current_words[-1]["end"]),
                )
            )

        return segments
