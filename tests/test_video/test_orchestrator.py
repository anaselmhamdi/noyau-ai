"""Tests for video generation orchestrator."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.llm import ClusterDistillOutput
from app.schemas.video import (
    CombinedVideoGenerationResult,
    CombinedVideoScript,
    CombinedVideoScriptResult,
    StorySegment,
    VideoGenerationResult,
    VideoScript,
    VideoScriptResult,
)
from app.video.orchestrator import (
    VideoConfigLocal,
    VideoFormatConfig,
    VideoStyleConfig,
    YouTubeConfigLocal,
    generate_combined_video,
    generate_single_video,
    generate_videos_for_issue,
)

pytestmark = pytest.mark.asyncio


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def sample_summary() -> ClusterDistillOutput:
    """Create a sample cluster summary."""
    return ClusterDistillOutput(
        headline="Test Headline for Video",
        teaser="Test teaser for the video script.",
        takeaway="Key takeaway from this story.",
        why_care="Why you should care about this.",
        bullets=["Point one", "Point two"],
        citations=[{"url": "https://example.com", "label": "Example"}],
        confidence="high",
    )


@pytest.fixture
def three_summaries() -> list[ClusterDistillOutput]:
    """Create three sample summaries."""
    return [
        ClusterDistillOutput(
            headline=f"Story {i} Headline",
            teaser=f"Teaser for story {i}.",
            takeaway=f"Takeaway {i}.",
            why_care=f"Why care {i}.",
            bullets=[f"Bullet {i}.1", f"Bullet {i}.2"],
            citations=[{"url": f"https://example{i}.com", "label": f"Source {i}"}],
            confidence="high",
        )
        for i in range(1, 4)
    ]


@pytest.fixture
def mock_video_config() -> VideoConfigLocal:
    """Create a mock video configuration."""
    return VideoConfigLocal(
        enabled=True,
        count=3,
        combined_mode=False,
        combined_duration_target=60,
        format=VideoFormatConfig(),
        style=VideoStyleConfig(),
        youtube=YouTubeConfigLocal(),
    )


@pytest.fixture
def mock_combined_config() -> VideoConfigLocal:
    """Create a mock config with combined mode enabled."""
    return VideoConfigLocal(
        enabled=True,
        count=3,
        combined_mode=True,
        combined_duration_target=60,
        format=VideoFormatConfig(),
        style=VideoStyleConfig(),
        youtube=YouTubeConfigLocal(),
    )


@pytest.fixture
def mock_video_script() -> VideoScript:
    """Create a mock video script."""
    return VideoScript(
        hook="Attention grabbing hook.",
        intro="Introduction to the story.",
        body="Main body content of the video.",
        cta="Call to action.",
        visual_keywords=["tech", "coding"],
        topic="dev",
    )


@pytest.fixture
def mock_combined_script() -> CombinedVideoScript:
    """Create a mock combined video script."""
    return CombinedVideoScript(
        hook="Three stories today.",
        intro="Your daily tech briefing.",
        stories=[
            StorySegment(
                story_number=1,
                transition="First up.",
                headline_text="Story One",
                body="Content for story one.",
                visual_keywords=["k8s"],
            ),
            StorySegment(
                story_number=2,
                transition="Next up.",
                headline_text="Story Two",
                body="Content for story two.",
                visual_keywords=["ai"],
            ),
            StorySegment(
                story_number=3,
                transition="Finally.",
                headline_text="Story Three",
                body="Content for story three.",
                visual_keywords=["security"],
            ),
        ],
        cta="Follow for updates.",
        topic="digest",
    )


@pytest.fixture
def mock_ranked_with_summaries(three_summaries):
    """Create mock ranked_with_summaries data structure."""
    results = []
    for i, summary in enumerate(three_summaries):
        # Structure: (identity, items, score_info, distill_result)
        mock_distill_result = MagicMock()
        mock_distill_result.output = summary
        results.append(
            (
                f"identity_{i}",
                [],  # items
                {"is_viral": False, "score": 0.8 - i * 0.1},  # score_info
                mock_distill_result,
            )
        )
    return results


# -----------------------------------------------------------------------------
# Config Tests
# -----------------------------------------------------------------------------


class TestVideoConfig:
    """Tests for video configuration."""

    def test_default_combined_mode_disabled(self, mock_video_config):
        """Combined mode should be disabled by default."""
        assert mock_video_config.combined_mode is False

    def test_combined_mode_can_be_enabled(self, mock_combined_config):
        """Combined mode can be enabled in config."""
        assert mock_combined_config.combined_mode is True

    def test_default_combined_duration_target(self, mock_combined_config):
        """Should have default combined duration target of 60 seconds."""
        assert mock_combined_config.combined_duration_target == 60


# -----------------------------------------------------------------------------
# Single Video Generation Tests
# -----------------------------------------------------------------------------


class TestGenerateSingleVideo:
    """Tests for single video generation."""

    async def test_generate_single_video_dry_run(
        self, sample_summary, mock_video_config, mock_video_script, tmp_path
    ):
        """Should return result without generating video in dry run mode."""
        with patch("app.video.orchestrator.generate_script") as mock_gen_script:
            mock_gen_script.return_value = VideoScriptResult(
                script=mock_video_script,
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            )

            result = await generate_single_video(
                summary=sample_summary,
                topic="dev",
                rank=1,
                issue_date=date(2026, 1, 13),
                cluster_id="test-cluster-id",
                output_dir=tmp_path,
                config=mock_video_config,
                db=None,
                dry_run=True,
            )

            assert result is not None
            assert result.video_path == "<dry-run>"
            assert result.script == mock_video_script

    async def test_generate_single_video_returns_none_on_script_failure(
        self, sample_summary, mock_video_config, tmp_path
    ):
        """Should return None if script generation fails."""
        with patch("app.video.orchestrator.generate_script", return_value=None):
            result = await generate_single_video(
                summary=sample_summary,
                topic="dev",
                rank=1,
                issue_date=date(2026, 1, 13),
                cluster_id="test-cluster-id",
                output_dir=tmp_path,
                config=mock_video_config,
                db=None,
                dry_run=False,
            )

            assert result is None


# -----------------------------------------------------------------------------
# Combined Video Generation Tests
# -----------------------------------------------------------------------------


class TestGenerateCombinedVideo:
    """Tests for combined video generation."""

    async def test_generate_combined_video_dry_run(
        self, three_summaries, mock_combined_config, mock_combined_script, tmp_path
    ):
        """Should return result without generating video in dry run mode."""
        with patch("app.video.orchestrator.generate_combined_script") as mock_gen_script:
            mock_gen_script.return_value = CombinedVideoScriptResult(
                script=mock_combined_script,
                prompt_tokens=300,
                completion_tokens=200,
                total_tokens=500,
            )

            result = await generate_combined_video(
                summaries=three_summaries,
                topics=["oss", "ai", "security"],
                issue_date=date(2026, 1, 13),
                cluster_ids=["id1", "id2", "id3"],
                output_dir=tmp_path,
                config=mock_combined_config,
                db=None,
                dry_run=True,
            )

            assert result is not None
            assert result.video_path == "<dry-run>"
            assert result.script == mock_combined_script
            assert len(result.story_headlines) == 3

    async def test_generate_combined_video_returns_none_on_script_failure(
        self, three_summaries, mock_combined_config, tmp_path
    ):
        """Should return None if combined script generation fails."""
        with patch("app.video.orchestrator.generate_combined_script", return_value=None):
            result = await generate_combined_video(
                summaries=three_summaries,
                topics=["oss", "ai", "security"],
                issue_date=date(2026, 1, 13),
                cluster_ids=["id1", "id2", "id3"],
                output_dir=tmp_path,
                config=mock_combined_config,
                db=None,
                dry_run=False,
            )

            assert result is None


# -----------------------------------------------------------------------------
# Routing Tests
# -----------------------------------------------------------------------------


class TestGenerateVideosForIssue:
    """Tests for generate_videos_for_issue routing."""

    async def test_routes_to_combined_when_enabled(
        self, mock_ranked_with_summaries, mock_combined_script, tmp_path
    ):
        """Should route to combined generation when combined_mode is True."""
        mock_config = VideoConfigLocal(
            enabled=True,
            count=3,
            combined_mode=True,
            combined_duration_target=60,
        )

        with (
            patch("app.video.orchestrator.get_video_config", return_value=mock_config),
            patch("app.video.orchestrator.generate_combined_video") as mock_combined,
        ):
            mock_combined.return_value = CombinedVideoGenerationResult(
                video_path=str(tmp_path / "combined.mp4"),
                duration_seconds=60.0,
                script=mock_combined_script,
                story_headlines=["H1", "H2", "H3"],
            )

            results = await generate_videos_for_issue(
                issue_date=date(2026, 1, 13),
                ranked_with_summaries=mock_ranked_with_summaries,
                db=None,
                dry_run=False,
            )

            # Should have called combined generation
            mock_combined.assert_called_once()
            assert len(results) == 1
            assert isinstance(results[0], CombinedVideoGenerationResult)

    async def test_routes_to_individual_when_disabled(
        self, mock_ranked_with_summaries, mock_video_script, tmp_path
    ):
        """Should route to individual generation when combined_mode is False."""
        mock_config = VideoConfigLocal(
            enabled=True,
            count=3,
            combined_mode=False,
            combined_duration_target=60,
        )

        with (
            patch("app.video.orchestrator.get_video_config", return_value=mock_config),
            patch("app.video.orchestrator.generate_single_video") as mock_single,
        ):
            mock_single.return_value = VideoGenerationResult(
                video_path=str(tmp_path / "video.mp4"),
                duration_seconds=45.0,
                script=mock_video_script,
            )

            results = await generate_videos_for_issue(
                issue_date=date(2026, 1, 13),
                ranked_with_summaries=mock_ranked_with_summaries,
                db=None,
                dry_run=False,
            )

            # Should have called single generation 3 times
            assert mock_single.call_count == 3
            assert len(results) == 3

    async def test_returns_empty_when_disabled(self, mock_ranked_with_summaries):
        """Should return empty list when video generation is disabled."""
        mock_config = VideoConfigLocal(
            enabled=False,
            count=3,
            combined_mode=False,
        )

        with patch("app.video.orchestrator.get_video_config", return_value=mock_config):
            results = await generate_videos_for_issue(
                issue_date=date(2026, 1, 13),
                ranked_with_summaries=mock_ranked_with_summaries,
                db=None,
                dry_run=False,
            )

            assert results == []

    async def test_combined_requires_3_summaries(self, tmp_path):
        """Should return empty if less than 3 stories available for combined mode."""
        mock_config = VideoConfigLocal(
            enabled=True,
            count=3,
            combined_mode=True,
            combined_duration_target=60,
        )

        # Only 2 items
        mock_distill = MagicMock()
        mock_distill.output = ClusterDistillOutput(
            headline="H",
            teaser="T",
            takeaway="K",
            bullets=["B1", "B2"],
            citations=[{"url": "https://example.com", "label": "Example"}],
            confidence="high",
        )
        short_list = [
            ("id1", [], {}, mock_distill),
            ("id2", [], {}, mock_distill),
        ]

        with patch("app.video.orchestrator.get_video_config", return_value=mock_config):
            results = await generate_videos_for_issue(
                issue_date=date(2026, 1, 13),
                ranked_with_summaries=short_list,
                db=None,
                dry_run=False,
            )

            assert results == []
