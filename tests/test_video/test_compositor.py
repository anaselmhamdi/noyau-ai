"""Tests for video compositor module."""

import pytest

from app.schemas.video import CombinedVideoScript, StorySegment, VideoScript
from app.video.compositor import (
    CombinedTimeline,
    _calculate_combined_timeline,
    _calculate_timeline,
)
from app.video.constants import (
    BRAND_INTRO_END,
    COMBINED_BRAND_INTRO_END,
    COMBINED_CTA_DURATION,
    COMBINED_HOOK_END,
    COMBINED_INTRO_END,
    HOOK_END,
    INTRO_END,
)

# -----------------------------------------------------------------------------
# Timeline Calculation Tests
# -----------------------------------------------------------------------------


class TestCalculateTimeline:
    """Tests for single-video timeline calculation."""

    def test_timeline_sections_are_sequential(self):
        """Timeline sections should be in order."""
        timeline = _calculate_timeline(total_duration=45.0)

        assert timeline.brand_intro_end <= timeline.hook_end
        assert timeline.hook_end <= timeline.intro_end
        assert timeline.intro_end <= timeline.body_end
        assert timeline.body_end <= timeline.total_duration

    def test_timeline_uses_constants(self):
        """Timeline should use predefined constants."""
        timeline = _calculate_timeline(total_duration=45.0)

        assert timeline.brand_intro_end == BRAND_INTRO_END
        assert timeline.hook_end == HOOK_END
        assert timeline.intro_end == INTRO_END

    def test_timeline_body_end_before_total(self):
        """Body should end before total duration (leaving room for CTA)."""
        timeline = _calculate_timeline(total_duration=45.0)

        assert timeline.body_end < timeline.total_duration

    def test_timeline_with_short_duration(self):
        """Should handle short durations gracefully."""
        timeline = _calculate_timeline(total_duration=20.0)

        # Should still produce valid timeline
        assert timeline.total_duration == 20.0
        assert timeline.brand_intro_end <= timeline.total_duration


class TestCalculateCombinedTimeline:
    """Tests for combined-video timeline calculation."""

    def test_combined_timeline_structure(self):
        """Should create proper timeline structure."""
        timeline = _calculate_combined_timeline(total_duration=60.0)

        assert isinstance(timeline, CombinedTimeline)
        assert timeline.brand_intro_end == COMBINED_BRAND_INTRO_END
        assert timeline.hook_end == COMBINED_HOOK_END
        assert timeline.intro_end == COMBINED_INTRO_END
        assert len(timeline.story_segments) == 3

    def test_combined_timeline_has_three_stories(self):
        """Should always have exactly 3 story segments."""
        timeline = _calculate_combined_timeline(total_duration=60.0)

        assert len(timeline.story_segments) == 3
        for segment in timeline.story_segments:
            assert isinstance(segment, tuple)
            assert len(segment) == 2  # (start, end)

    def test_combined_timeline_stories_are_sequential(self):
        """Story segments should not overlap."""
        timeline = _calculate_combined_timeline(total_duration=60.0)

        for i in range(len(timeline.story_segments) - 1):
            current_end = timeline.story_segments[i][1]
            next_start = timeline.story_segments[i + 1][0]
            assert current_end == pytest.approx(next_start, rel=0.01)

    def test_combined_timeline_stories_start_after_intro(self):
        """Stories should start after intro section."""
        timeline = _calculate_combined_timeline(total_duration=60.0)

        first_story_start = timeline.story_segments[0][0]
        assert first_story_start == timeline.intro_end

    def test_combined_timeline_stories_end_before_cta(self):
        """Stories should end before CTA section."""
        timeline = _calculate_combined_timeline(total_duration=60.0)

        last_story_end = timeline.story_segments[2][1]
        assert last_story_end == pytest.approx(timeline.cta_start, rel=0.01)

    def test_combined_timeline_cta_duration(self):
        """CTA section should have correct duration."""
        timeline = _calculate_combined_timeline(total_duration=60.0)

        cta_duration = timeline.total_duration - timeline.cta_start
        assert cta_duration == pytest.approx(COMBINED_CTA_DURATION, rel=0.01)

    def test_combined_timeline_equal_story_durations(self):
        """Story segments should have approximately equal durations."""
        timeline = _calculate_combined_timeline(total_duration=60.0)

        durations = [segment[1] - segment[0] for segment in timeline.story_segments]

        # All durations should be within 1% of each other
        avg_duration = sum(durations) / len(durations)
        for duration in durations:
            assert duration == pytest.approx(avg_duration, rel=0.01)

    def test_combined_timeline_longer_duration(self):
        """Should scale properly for longer videos."""
        timeline = _calculate_combined_timeline(total_duration=90.0)

        # Stories should get more time, but intro/outro stay fixed
        assert timeline.intro_end == COMBINED_INTRO_END  # Fixed
        assert timeline.total_duration == 90.0

        # Each story should get more time
        story_duration = timeline.story_segments[0][1] - timeline.story_segments[0][0]
        assert story_duration > 15  # Should be longer than in 60s video

    def test_combined_timeline_total_duration_matches(self):
        """Total duration should match input."""
        for duration in [45.0, 60.0, 75.0, 90.0]:
            timeline = _calculate_combined_timeline(total_duration=duration)
            assert timeline.total_duration == duration


# -----------------------------------------------------------------------------
# Fixtures for Composition Tests
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_video_script() -> VideoScript:
    """Create a mock video script."""
    return VideoScript(
        hook="This changes everything.",
        intro="Big news in tech today.",
        body="Here's what you need to know about the latest developments.",
        cta="Follow for more.",
        visual_keywords=["technology", "coding"],
        topic="dev",
    )


@pytest.fixture
def mock_combined_script() -> CombinedVideoScript:
    """Create a mock combined video script."""
    return CombinedVideoScript(
        hook="Three stories today.",
        intro="Your daily briefing.",
        stories=[
            StorySegment(
                story_number=1,
                transition="First up.",
                headline_text="Story One Headline",
                body="Content for story one.",
                visual_keywords=["tech"],
            ),
            StorySegment(
                story_number=2,
                transition="Next up.",
                headline_text="Story Two Headline",
                body="Content for story two.",
                visual_keywords=["coding"],
            ),
            StorySegment(
                story_number=3,
                transition="And finally.",
                headline_text="Story Three Headline",
                body="Content for story three.",
                visual_keywords=["security"],
            ),
        ],
        cta="Follow for updates.",
        topic="digest",
    )


# -----------------------------------------------------------------------------
# Schema Validation Tests
# -----------------------------------------------------------------------------


class TestCombinedVideoScript:
    """Tests for CombinedVideoScript schema."""

    def test_requires_exactly_three_stories(self):
        """Should require exactly 3 story segments."""
        # Valid with 3 stories
        script = CombinedVideoScript(
            hook="Hook",
            intro="Intro",
            stories=[
                StorySegment(
                    story_number=i,
                    transition=f"Trans {i}",
                    headline_text=f"Headline {i}",
                    body=f"Body {i}",
                    visual_keywords=["kw"],
                )
                for i in range(1, 4)
            ],
            cta="CTA",
        )
        assert len(script.stories) == 3

    def test_story_segment_fields(self, mock_combined_script):
        """Story segments should have all required fields."""
        for story in mock_combined_script.stories:
            assert hasattr(story, "story_number")
            assert hasattr(story, "transition")
            assert hasattr(story, "headline_text")
            assert hasattr(story, "body")
            assert hasattr(story, "visual_keywords")

    def test_default_topic_is_digest(self, mock_combined_script):
        """Combined scripts should default to 'digest' topic."""
        assert mock_combined_script.topic == "digest"
