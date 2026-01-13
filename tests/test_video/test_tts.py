"""Tests for TTS module."""

import pytest

from app.schemas.video import CombinedVideoScript, StorySegment, VideoScript
from app.video.tts.base import TTSProvider

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def sample_script() -> VideoScript:
    """Create a sample video script."""
    return VideoScript(
        hook="This changes everything.",
        intro="Python 3.14 just dropped with major improvements.",
        body="The new JIT compiler makes numeric code 20% faster. "
        "Error messages are now clearer than ever.",
        cta="Follow for daily tech updates.",
        visual_keywords=["python", "coding"],
        topic="oss",
    )


@pytest.fixture
def sample_combined_script() -> CombinedVideoScript:
    """Create a sample combined video script."""
    return CombinedVideoScript(
        hook="Three stories shaking up tech today.",
        intro="Here's your daily briefing.",
        stories=[
            StorySegment(
                story_number=1,
                transition="First up.",
                headline_text="K8s 1.30 Released",
                body="Kubernetes 1.30 brings Pod Security improvements.",
                visual_keywords=["kubernetes", "cloud"],
            ),
            StorySegment(
                story_number=2,
                transition="Next up.",
                headline_text="GPT-5 Launches",
                body="OpenAI's GPT-5 can process multimodal content.",
                visual_keywords=["ai", "openai"],
            ),
            StorySegment(
                story_number=3,
                transition="And finally.",
                headline_text="Critical CVE Alert",
                body="A vulnerability in lodash affects millions.",
                visual_keywords=["security", "npm"],
            ),
        ],
        cta="Follow for your daily tech briefing.",
        topic="digest",
    )


# -----------------------------------------------------------------------------
# TTS Formatting Tests
# -----------------------------------------------------------------------------


class TestTTSFormatting:
    """Tests for TTS script formatting."""

    def test_format_script_includes_brand_intro(self, sample_script):
        """Should include brand intro at the start."""

        class TestTTS(TTSProvider):
            async def synthesize(self, text, output_path):
                pass

        tts = TestTTS()
        text = tts.format_script_for_narration(sample_script)

        assert text.startswith(tts.BRAND_INTRO)

    def test_format_script_includes_brand_outro(self, sample_script):
        """Should include brand outro at the end."""

        class TestTTS(TTSProvider):
            async def synthesize(self, text, output_path):
                pass

        tts = TestTTS()
        text = tts.format_script_for_narration(sample_script)

        assert text.endswith(tts.BRAND_OUTRO)

    def test_format_script_includes_all_sections(self, sample_script):
        """Should include hook, intro, body, and CTA."""

        class TestTTS(TTSProvider):
            async def synthesize(self, text, output_path):
                pass

        tts = TestTTS()
        text = tts.format_script_for_narration(sample_script)

        assert sample_script.hook in text
        assert sample_script.intro in text
        assert sample_script.body in text
        assert sample_script.cta in text

    def test_format_script_includes_pauses(self, sample_script):
        """Should include pause markers between sections."""

        class TestTTS(TTSProvider):
            async def synthesize(self, text, output_path):
                pass

        tts = TestTTS()
        text = tts.format_script_for_narration(sample_script)

        # Should have multiple pauses
        assert text.count("...") >= 4


class TestCombinedTTSFormatting:
    """Tests for combined script TTS formatting."""

    def test_format_combined_includes_brand_intro(self, sample_combined_script):
        """Should include brand intro at the start."""

        class TestTTS(TTSProvider):
            async def synthesize(self, text, output_path):
                pass

        tts = TestTTS()
        text = tts.format_combined_script_for_narration(sample_combined_script)

        assert text.startswith(tts.BRAND_INTRO)

    def test_format_combined_includes_brand_outro(self, sample_combined_script):
        """Should include brand outro at the end."""

        class TestTTS(TTSProvider):
            async def synthesize(self, text, output_path):
                pass

        tts = TestTTS()
        text = tts.format_combined_script_for_narration(sample_combined_script)

        assert text.endswith(tts.BRAND_OUTRO)

    def test_format_combined_includes_hook_and_intro(self, sample_combined_script):
        """Should include hook and intro sections."""

        class TestTTS(TTSProvider):
            async def synthesize(self, text, output_path):
                pass

        tts = TestTTS()
        text = tts.format_combined_script_for_narration(sample_combined_script)

        assert sample_combined_script.hook in text
        assert sample_combined_script.intro in text

    def test_format_combined_includes_all_stories(self, sample_combined_script):
        """Should include all story transitions and bodies."""

        class TestTTS(TTSProvider):
            async def synthesize(self, text, output_path):
                pass

        tts = TestTTS()
        text = tts.format_combined_script_for_narration(sample_combined_script)

        for story in sample_combined_script.stories:
            assert story.transition in text
            assert story.body in text

    def test_format_combined_includes_cta(self, sample_combined_script):
        """Should include CTA section."""

        class TestTTS(TTSProvider):
            async def synthesize(self, text, output_path):
                pass

        tts = TestTTS()
        text = tts.format_combined_script_for_narration(sample_combined_script)

        assert sample_combined_script.cta in text

    def test_format_combined_has_pauses_between_stories(self, sample_combined_script):
        """Should have pause markers between story sections."""

        class TestTTS(TTSProvider):
            async def synthesize(self, text, output_path):
                pass

        tts = TestTTS()
        text = tts.format_combined_script_for_narration(sample_combined_script)

        # Should have pauses: after brand intro, hook, intro, each story (x3), before outro
        # At minimum: 2 (intro) + 6 (3 stories x 2) + 2 (outro) = 10 pauses
        assert text.count("...") >= 8

    def test_format_combined_story_order(self, sample_combined_script):
        """Should maintain correct story order in output."""

        class TestTTS(TTSProvider):
            async def synthesize(self, text, output_path):
                pass

        tts = TestTTS()
        text = tts.format_combined_script_for_narration(sample_combined_script)

        # Check story transitions appear in order
        first_up_pos = text.find("First up.")
        next_up_pos = text.find("Next up.")
        finally_pos = text.find("And finally.")

        assert first_up_pos < next_up_pos < finally_pos
