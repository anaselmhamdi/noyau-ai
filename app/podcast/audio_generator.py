"""Audio generation for podcasts using TTS and background music."""

from pathlib import Path
from tempfile import TemporaryDirectory

from moviepy import AudioFileClip, CompositeAudioClip, concatenate_audioclips

from app.config import get_settings
from app.core.logging import get_logger
from app.schemas.podcast import ChapterMarker, PodcastAudioResult, PodcastScript
from app.video.background_music import fetch_background_music
from app.video.tts.openai_tts import OpenAITTS

logger = get_logger(__name__)

# Branded intro/outro for podcast
PODCAST_INTRO = "Welcome to Noyau Daily, your daily briefing on what matters in tech."
PODCAST_OUTRO = (
    "That's all for today's Noyau Daily. "
    "If you found this helpful, subscribe wherever you get your podcasts. "
    "See you tomorrow."
)


class PodcastAudioGenerator:
    """
    Generate podcast audio from scripts using OpenAI TTS.

    Handles:
    - Per-section TTS generation for chapter markers
    - Audio concatenation with pauses
    - Background music mixing
    - MP3 export with metadata
    """

    def __init__(
        self,
        voice: str = "nova",
        model: str = "tts-1-hd",
        background_volume: float = 0.03,
    ):
        """
        Initialize the audio generator.

        Args:
            voice: OpenAI TTS voice (nova, alloy, echo, fable, onyx, shimmer)
            model: OpenAI TTS model (tts-1 or tts-1-hd)
            background_volume: Volume level for background music (0.0-1.0)
        """
        settings = get_settings()
        self.tts = OpenAITTS(voice=voice, model=model, api_key=settings.openai_api_key)
        self.background_volume = background_volume

    async def generate(
        self,
        script: PodcastScript,
        output_path: Path,
        include_background_music: bool = True,
    ) -> PodcastAudioResult | None:
        """
        Generate podcast audio from a script.

        Args:
            script: Podcast script with intro, stories, and outro
            output_path: Path to save the final audio file
            include_background_music: Whether to mix in background music

        Returns:
            PodcastAudioResult with audio path, duration, and chapters
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            audio_segments: list[AudioFileClip] = []
            chapters: list[ChapterMarker] = []
            current_time = 0.0

            # Generate branded intro
            intro_result = await self._generate_section(
                f"{PODCAST_INTRO} ... {script.intro}",
                temp_path / "intro.mp3",
            )
            if intro_result:
                audio_segments.append(intro_result)
                chapters.append(
                    ChapterMarker(
                        title="Introduction",
                        start_time=current_time,
                        end_time=current_time + intro_result.duration,
                    )
                )
                current_time += intro_result.duration

            # Generate each story segment
            for i, story in enumerate(script.stories, start=1):
                # Combine transition, body, and attribution into one segment
                story_text = f"{story.transition} ... {story.body} ... {story.source_attribution}"
                story_result = await self._generate_section(
                    story_text,
                    temp_path / f"story_{i}.mp3",
                )
                if story_result:
                    audio_segments.append(story_result)
                    # Use headline for chapter title, truncate if needed
                    chapter_title = (
                        story.headline[:50] if len(story.headline) > 50 else story.headline
                    )
                    chapters.append(
                        ChapterMarker(
                            title=chapter_title,
                            start_time=current_time,
                            end_time=current_time + story_result.duration,
                        )
                    )
                    current_time += story_result.duration

            # Generate branded outro
            outro_result = await self._generate_section(
                f"{script.outro} ... {PODCAST_OUTRO}",
                temp_path / "outro.mp3",
            )
            if outro_result:
                audio_segments.append(outro_result)
                chapters.append(
                    ChapterMarker(
                        title="Outro",
                        start_time=current_time,
                        end_time=current_time + outro_result.duration,
                    )
                )
                current_time += outro_result.duration

            if not audio_segments:
                logger.error("podcast_audio_no_segments_generated")
                return None

            # Concatenate all segments
            logger.bind(segment_count=len(audio_segments)).info("podcast_audio_concatenating")
            combined_audio = concatenate_audioclips(audio_segments)

            # Mix with background music if enabled
            if include_background_music:
                combined_audio = await self._mix_background_music(
                    combined_audio,
                    combined_audio.duration,
                    temp_path,
                )

            # Write final audio file
            combined_audio.write_audiofile(
                str(output_path),
                fps=44100,
                nbytes=2,
                codec="libmp3lame",
                bitrate="192k",
                logger=None,
            )

            # Clean up
            combined_audio.close()
            for segment in audio_segments:
                segment.close()

            logger.bind(
                output=str(output_path),
                duration=current_time,
                chapter_count=len(chapters),
            ).info("podcast_audio_generated")

            return PodcastAudioResult(
                audio_path=str(output_path),
                duration_seconds=current_time,
                chapters=chapters,
            )

    async def _generate_section(
        self,
        text: str,
        output_path: Path,
    ) -> AudioFileClip | None:
        """Generate TTS for a single section."""
        result = await self.tts.synthesize(text, output_path)
        if result:
            return AudioFileClip(str(result.audio_path))
        return None

    async def _mix_background_music(
        self,
        narration: AudioFileClip,
        duration: float,
        temp_dir: Path,
    ) -> AudioFileClip | CompositeAudioClip:
        """
        Mix narration with background music.

        Args:
            narration: Main narration audio
            duration: Total duration needed
            temp_dir: Temporary directory for music download

        Returns:
            Mixed audio clip
        """
        # Fetch ambient/podcast-style background music
        music_path = await fetch_background_music(
            topic="general",  # Neutral ambient for podcasts
            duration_needed=duration,
            output_dir=temp_dir,
        )

        if not music_path:
            logger.warning("podcast_background_music_unavailable")
            return narration

        try:
            background = AudioFileClip(str(music_path))

            # Loop if needed
            if background.duration < duration:
                loops_needed = int(duration / background.duration) + 1
                background = concatenate_audioclips([background] * loops_needed)

            # Trim to match narration
            background = background.subclipped(0, duration)

            # Apply volume reduction
            background = background.with_volume_scaled(self.background_volume)

            # Mix tracks
            mixed = CompositeAudioClip([narration, background])

            logger.info("podcast_audio_mixed_with_background")
            return mixed

        except Exception as e:
            logger.bind(error=str(e)).warning("podcast_background_music_mixing_failed")
            return narration


def format_podcast_script_for_narration(script: PodcastScript) -> str:
    """
    Format a podcast script as a single text block for TTS.

    Useful for generating the entire podcast in one TTS call
    if chapter markers are not needed.
    """
    parts = [
        PODCAST_INTRO,
        "...",
        script.intro,
        "...",
    ]

    for story in script.stories:
        parts.extend(
            [
                story.transition,
                "...",
                story.body,
                "...",
                story.source_attribution,
                "...",
            ]
        )

    parts.extend(
        [
            script.outro,
            "...",
            PODCAST_OUTRO,
        ]
    )

    return " ".join(parts)


def estimate_audio_duration(script: PodcastScript) -> float:
    """
    Estimate audio duration from a podcast script.

    Assumes ~150 words per minute speaking rate (2.5 words/second).
    """
    text = format_podcast_script_for_narration(script)
    word_count = len(text.split())
    return word_count / 2.5  # seconds
