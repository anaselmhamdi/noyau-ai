"""Text-to-speech providers for video narration.

This package provides TTS synthesis with subtitle generation for video production.
"""

from app.video.tts.base import SubtitleSegment, TTSProvider, TTSResult
from app.video.tts.edge_tts import EdgeTTS
from app.video.tts.elevenlabs_tts import ElevenLabsTTS
from app.video.tts.openai_tts import OpenAITTS
from app.video.tts.utils import (
    generate_srt,
    get_tts_provider,
    synthesize_combined_script,
    synthesize_script,
)

__all__ = [
    "EdgeTTS",
    "ElevenLabsTTS",
    "OpenAITTS",
    "SubtitleSegment",
    "TTSProvider",
    "TTSResult",
    "generate_srt",
    "get_tts_provider",
    "synthesize_combined_script",
    "synthesize_script",
]
