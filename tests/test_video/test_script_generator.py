"""Tests for video script generation."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.llm import ClusterDistillOutput
from app.schemas.video import CombinedVideoScript, StorySegment, VideoScript
from app.video.script_generator import (
    estimate_combined_script_duration,
    estimate_script_duration,
    generate_combined_script,
    generate_script,
)

pytestmark = pytest.mark.asyncio


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def sample_summary() -> ClusterDistillOutput:
    """Create a sample cluster summary for testing."""
    return ClusterDistillOutput(
        headline="Python 3.14 Released with Major Performance Improvements",
        teaser="The latest Python version brings a 20% speed boost and new async features.",
        takeaway="Upgrade your projects to benefit from faster execution.",
        why_care="Directly impacts your development workflow.",
        bullets=[
            "New JIT compiler for numeric workloads",
            "Improved error messages for easier debugging",
        ],
        citations=[{"url": "https://python.org/release", "label": "Python.org"}],
        confidence="high",
    )


@pytest.fixture
def three_summaries() -> list[ClusterDistillOutput]:
    """Create three sample summaries for combined video testing."""
    return [
        ClusterDistillOutput(
            headline="Kubernetes 1.30 Released with Enhanced Security Features",
            teaser="The new K8s version includes Pod Security Admission improvements.",
            takeaway="Review your pod security policies for the upgrade.",
            why_care="Critical for production workloads.",
            bullets=["Pod Security Admission GA", "Improved API server performance"],
            citations=[{"url": "https://kubernetes.io", "label": "K8s Blog"}],
            confidence="high",
        ),
        ClusterDistillOutput(
            headline="OpenAI Launches GPT-5 with Multimodal Reasoning",
            teaser="The new model can process text, images, and video simultaneously.",
            takeaway="Explore new use cases for your AI applications.",
            why_care="Game-changer for AI development.",
            bullets=["10x context window", "Native function calling"],
            citations=[{"url": "https://openai.com/blog", "label": "OpenAI Blog"}],
            confidence="high",
        ),
        ClusterDistillOutput(
            headline="Critical CVE Found in Popular NPM Package",
            teaser="A vulnerability in lodash affects millions of projects.",
            takeaway="Update your dependencies immediately.",
            why_care="Your projects may be affected.",
            bullets=["Remote code execution possible", "Patch available now"],
            citations=[{"url": "https://nvd.nist.gov", "label": "NVD"}],
            confidence="medium",
        ),
    ]


@pytest.fixture
def mock_video_script() -> VideoScript:
    """Create a mock video script."""
    return VideoScript(
        hook="Python just got 20% faster.",
        intro="The Python team just released version 3.14, and it's a big deal.",
        body="The new JIT compiler targets numeric workloads, making data science "
        "and ML code significantly faster. Plus, error messages are now clearer "
        "than ever, helping you debug faster.",
        cta="Follow for daily tech updates.",
        visual_keywords=["python", "coding", "performance", "data science"],
        topic="oss",
    )


@pytest.fixture
def mock_combined_script() -> CombinedVideoScript:
    """Create a mock combined video script."""
    return CombinedVideoScript(
        hook="Three stories shaking up tech today.",
        intro="Here's your daily tech briefing.",
        stories=[
            StorySegment(
                story_number=1,
                transition="First up.",
                headline_text="Kubernetes 1.30 Security Update",
                body="Kubernetes 1.30 brings major security improvements with Pod Security "
                "Admission now GA. Review your pod security policies before upgrading.",
                visual_keywords=["kubernetes", "cloud", "security"],
            ),
            StorySegment(
                story_number=2,
                transition="Next up.",
                headline_text="GPT-5 Goes Multimodal",
                body="OpenAI's GPT-5 can now process text, images, and video together. "
                "The context window is 10 times larger, opening up new possibilities.",
                visual_keywords=["ai", "openai", "technology"],
            ),
            StorySegment(
                story_number=3,
                transition="And finally.",
                headline_text="Critical NPM Vulnerability",
                body="A severe vulnerability in lodash affects millions of projects. "
                "Update your dependencies now to avoid remote code execution attacks.",
                visual_keywords=["security", "coding", "npm"],
            ),
        ],
        cta="Follow for your daily tech briefing.",
        topic="digest",
    )


# -----------------------------------------------------------------------------
# Single Video Script Tests
# -----------------------------------------------------------------------------


class TestGenerateScript:
    """Tests for single-story video script generation."""

    async def test_generate_script_success(self, sample_summary, mock_video_script):
        """Should generate a video script from summary."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.parsed = mock_video_script
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 200
        mock_response.usage.completion_tokens = 150
        mock_response.usage.total_tokens = 350
        mock_client.beta.chat.completions.parse = AsyncMock(return_value=mock_response)

        result = await generate_script(
            summary=sample_summary,
            topic="oss",
            rank=1,
            client=mock_client,
        )

        assert result is not None
        assert result.script.hook == "Python just got 20% faster."
        assert result.script.topic == "oss"
        assert result.total_tokens == 350

    async def test_generate_script_returns_none_on_error(self, sample_summary):
        """Should return None when API call fails."""
        mock_client = AsyncMock()
        mock_client.beta.chat.completions.parse = AsyncMock(side_effect=Exception("API Error"))

        result = await generate_script(
            summary=sample_summary,
            topic="dev",
            rank=1,
            client=mock_client,
        )

        assert result is None

    async def test_generate_script_returns_none_on_empty_response(self, sample_summary):
        """Should return None when LLM returns no parsed content."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.parsed = None
        mock_client.beta.chat.completions.parse = AsyncMock(return_value=mock_response)

        result = await generate_script(
            summary=sample_summary,
            topic="dev",
            rank=1,
            client=mock_client,
        )

        assert result is None


class TestEstimateScriptDuration:
    """Tests for script duration estimation."""

    def test_estimates_duration_from_word_count(self, mock_video_script):
        """Should estimate duration based on words (2.5 words/second)."""
        duration = estimate_script_duration(mock_video_script)

        # Count total words in script
        total_words = (
            len(mock_video_script.hook.split())
            + len(mock_video_script.intro.split())
            + len(mock_video_script.body.split())
            + len(mock_video_script.cta.split())
        )
        expected_duration = total_words / 2.5

        assert duration == expected_duration
        # Should be roughly 15-30 seconds for a typical script
        assert 10 < duration < 60


# -----------------------------------------------------------------------------
# Combined Video Script Tests
# -----------------------------------------------------------------------------


class TestGenerateCombinedScript:
    """Tests for combined 3-story video script generation."""

    async def test_generate_combined_script_success(self, three_summaries, mock_combined_script):
        """Should generate a combined script from 3 summaries."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.parsed = mock_combined_script
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 500
        mock_response.usage.completion_tokens = 400
        mock_response.usage.total_tokens = 900
        mock_client.beta.chat.completions.parse = AsyncMock(return_value=mock_response)

        result = await generate_combined_script(
            summaries=three_summaries,
            topics=["oss", "ai", "security"],
            client=mock_client,
        )

        assert result is not None
        assert result.script.hook == "Three stories shaking up tech today."
        assert len(result.script.stories) == 3
        assert result.script.stories[0].story_number == 1
        assert result.script.stories[1].transition == "Next up."
        assert result.script.topic == "digest"
        assert result.total_tokens == 900

    async def test_generate_combined_script_requires_3_summaries(self, sample_summary):
        """Should return None if less than 3 summaries provided."""
        mock_client = AsyncMock()

        result = await generate_combined_script(
            summaries=[sample_summary, sample_summary],  # Only 2
            topics=["dev", "ai"],
            client=mock_client,
        )

        assert result is None
        # Should not call the API
        mock_client.beta.chat.completions.parse.assert_not_called()

    async def test_generate_combined_script_returns_none_on_error(self, three_summaries):
        """Should return None when API call fails."""
        mock_client = AsyncMock()
        mock_client.beta.chat.completions.parse = AsyncMock(side_effect=Exception("API Error"))

        result = await generate_combined_script(
            summaries=three_summaries,
            topics=["oss", "ai", "security"],
            client=mock_client,
        )

        assert result is None

    async def test_generate_combined_script_returns_none_on_empty_response(self, three_summaries):
        """Should return None when LLM returns no parsed content."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.parsed = None
        mock_client.beta.chat.completions.parse = AsyncMock(return_value=mock_response)

        result = await generate_combined_script(
            summaries=three_summaries,
            topics=["oss", "ai", "security"],
            client=mock_client,
        )

        assert result is None


class TestEstimateCombinedScriptDuration:
    """Tests for combined script duration estimation."""

    def test_estimates_combined_duration(self, mock_combined_script):
        """Should estimate duration for combined script."""
        duration = estimate_combined_script_duration(mock_combined_script)

        # Should be roughly 45-75 seconds for a combined script
        assert 30 < duration < 90

    def test_includes_all_sections(self, mock_combined_script):
        """Should include hook, intro, all stories, and CTA in duration."""
        duration = estimate_combined_script_duration(mock_combined_script)

        # Calculate expected manually
        words = (
            len(mock_combined_script.hook.split())
            + len(mock_combined_script.intro.split())
            + len(mock_combined_script.cta.split())
        )
        for story in mock_combined_script.stories:
            words += len(story.transition.split()) + len(story.body.split())

        expected = words / 2.5
        assert duration == expected
