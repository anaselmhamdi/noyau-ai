"""
Tests for Twitter service.

Tests tweet formatting, character limits, thread posting logic,
and graceful degradation patterns.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.twitter_service import (
    ThreadResult,
    TweetResult,
    _extract_primary_source_url,
    build_intro_tweet,
    build_story_tweet,
    post_twitter_thread,
    send_twitter_digest,
)


class TestTweetFormatting:
    """Tests for tweet text formatting."""

    def test_build_intro_tweet_contains_date(self):
        """Intro tweet includes formatted date."""
        result = build_intro_tweet(date(2026, 1, 11))
        assert "January 11, 2026" in result

    def test_build_intro_tweet_under_char_limit(self):
        """Intro tweet stays under 280 chars."""
        result = build_intro_tweet(date(2026, 1, 11))
        assert len(result) <= 280

    def test_build_intro_tweet_contains_hook(self):
        """Intro tweet contains engaging hook."""
        result = build_intro_tweet(date(2026, 1, 11))
        assert "↓" in result or "Thread" in result

    def test_build_story_tweet_includes_rank(self):
        """Story tweet includes rank prefix."""
        item = {
            "headline": "Test Headline",
            "teaser": "Test teaser.",
            "citations": [],
        }
        result = build_story_tweet(1, item)
        assert "1/10:" in result

    def test_build_story_tweet_includes_headline(self):
        """Story tweet includes the headline."""
        item = {
            "headline": "Important Tech News",
            "teaser": "Some details here.",
            "citations": [],
        }
        result = build_story_tweet(5, item)
        assert "Important Tech News" in result

    def test_build_story_tweet_includes_teaser(self):
        """Story tweet includes the teaser when space allows."""
        item = {
            "headline": "Short",
            "teaser": "This is a short teaser.",
            "citations": [],
        }
        result = build_story_tweet(1, item)
        assert "This is a short teaser." in result

    def test_build_story_tweet_under_char_limit(self):
        """Story tweet stays under 280 chars."""
        item = {
            "headline": "Test Headline",
            "teaser": "Test teaser content.",
            "citations": [{"url": "https://example.com", "label": "Source"}],
        }
        result = build_story_tweet(10, item)
        assert len(result) <= 280

    def test_build_story_tweet_truncates_long_teaser(self):
        """Long teaser is truncated to fit limit."""
        item = {
            "headline": "Normal Headline Here",
            "teaser": "A" * 300,
            "citations": [{"url": "https://example.com", "label": "Source"}],
        }
        result = build_story_tweet(1, item)
        assert len(result) <= 280
        assert "..." in result

    def test_build_story_tweet_preserves_headline_when_long(self):
        """Headline is preserved even with long teaser."""
        item = {
            "headline": "Important Headline Must Stay",
            "teaser": "X" * 250,
            "citations": [],
        }
        result = build_story_tweet(1, item)
        assert "Important Headline Must Stay" in result

    def test_build_story_tweet_includes_url(self):
        """Story tweet includes source URL."""
        item = {
            "headline": "Test",
            "teaser": "Teaser",
            "citations": [{"url": "https://example.com/article", "label": "Source"}],
        }
        result = build_story_tweet(1, item)
        assert "https://example.com/article" in result

    def test_build_story_tweet_no_citations(self):
        """Story tweet works without citations."""
        item = {
            "headline": "Headline Without URL",
            "teaser": "Some teaser text here.",
            "citations": [],
        }
        result = build_story_tweet(1, item)
        assert len(result) <= 280
        assert "Headline Without URL" in result


class TestSourceExtraction:
    """Tests for URL extraction from citations."""

    def test_extract_primary_url(self):
        """Extracts first citation URL."""
        citations = [
            {"url": "https://first.com", "label": "First"},
            {"url": "https://second.com", "label": "Second"},
        ]
        result = _extract_primary_source_url(citations)
        assert result == "https://first.com"

    def test_extract_empty_citations(self):
        """Returns empty string for no citations."""
        result = _extract_primary_source_url([])
        assert result == ""

    def test_extract_none_citations(self):
        """Handles None citations gracefully."""
        result = _extract_primary_source_url(None)
        assert result == ""

    def test_extract_malformed_citations(self):
        """Handles malformed citation dicts."""
        citations = [{"label": "No URL"}]
        result = _extract_primary_source_url(citations)
        assert result == ""

    def test_extract_skips_empty_urls(self):
        """Skips citations with empty URLs."""
        citations = [
            {"url": "", "label": "Empty"},
            {"url": "https://valid.com", "label": "Valid"},
        ]
        result = _extract_primary_source_url(citations)
        assert result == "https://valid.com"


class TestGracefulDegradation:
    """Tests for error handling and graceful degradation."""

    @pytest.mark.asyncio
    async def test_disabled_returns_false(self):
        """Disabled Twitter returns False without errors."""
        with patch("app.services.twitter_service.get_config") as mock_config:
            mock_config.return_value.twitter.enabled = False

            result = await send_twitter_digest(date.today(), [])

            assert result is False

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_false(self):
        """Missing API key returns False with warning."""
        with patch("app.services.twitter_service.get_config") as mock_config:
            mock_config.return_value.twitter.enabled = True
            mock_config.return_value.twitter.api_key = ""
            mock_config.return_value.twitter.access_token = "token"

            result = await send_twitter_digest(date.today(), [])

            assert result is False

    @pytest.mark.asyncio
    async def test_missing_access_token_returns_false(self):
        """Missing access token returns False with warning."""
        with patch("app.services.twitter_service.get_config") as mock_config:
            mock_config.return_value.twitter.enabled = True
            mock_config.return_value.twitter.api_key = "key"
            mock_config.return_value.twitter.access_token = ""

            result = await send_twitter_digest(date.today(), [])

            assert result is False


class TestThreadPosting:
    """Tests for thread posting logic."""

    @pytest.fixture
    def sample_items(self):
        """Sample issue items for testing."""
        return [
            {
                "headline": f"Story {i} Headline",
                "teaser": f"Story {i} teaser text here.",
                "citations": [{"url": f"https://example{i}.com", "label": "Source"}],
            }
            for i in range(1, 11)
        ]

    @pytest.fixture
    def mock_config(self):
        """Mock config for testing."""
        config = MagicMock()
        config.twitter.enabled = True
        config.twitter.api_key = "test-api-key"
        config.twitter.api_secret = "test-api-secret"
        config.twitter.access_token = "test-access-token"
        config.twitter.access_token_secret = "test-access-token-secret"
        config.twitter.intro_template = "{date} Tech Briefing\n\nLet's go ↓"
        config.twitter.outro_template = "That's your daily briefing.\n\nnoyau.news"
        config.twitter.max_retries = 3
        config.twitter.retry_delay_seconds = 1
        return config

    @pytest.mark.asyncio
    async def test_thread_returns_success_on_all_posted(self, sample_items, mock_config):
        """Thread returns success when all tweets post successfully."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"data": {"id": "12345"}}

        with (
            patch("app.services.twitter_service.get_config", return_value=mock_config),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await post_twitter_thread(date(2026, 1, 11), sample_items)

            assert result.success is True
            assert result.intro_tweet_id == "12345"
            # 1 intro + 10 stories + 1 outro = 12 posts
            assert mock_client.post.call_count == 12

    @pytest.mark.asyncio
    async def test_thread_fails_when_intro_fails(self, sample_items, mock_config):
        """Thread fails when intro tweet fails to post."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with (
            patch("app.services.twitter_service.get_config", return_value=mock_config),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await post_twitter_thread(date(2026, 1, 11), sample_items)

            assert result.success is False
            assert result.intro_tweet_id is None
            assert "Authentication failed" in result.message

    @pytest.mark.asyncio
    async def test_thread_partial_success(self, sample_items, mock_config):
        """Thread reports partial success when some tweets fail."""
        success_response = MagicMock()
        success_response.status_code = 201
        success_response.json.return_value = {"data": {"id": "12345"}}

        fail_response = MagicMock()
        fail_response.status_code = 500
        fail_response.text = "Internal Server Error"

        call_count = [0]

        def mock_post(*args, **kwargs):
            call_count[0] += 1
            # Fail every 3rd story tweet (calls 4, 7, 10)
            if call_count[0] in [4, 7, 10]:
                return fail_response
            return success_response

        with (
            patch("app.services.twitter_service.get_config", return_value=mock_config),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            mock_client = AsyncMock()
            mock_client.post.side_effect = mock_post
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await post_twitter_thread(date(2026, 1, 11), sample_items)

            # Should still be partial success
            assert result.success is True
            assert result.intro_tweet_id == "12345"
            assert "Partial" in result.message


class TestTweetResult:
    """Tests for TweetResult dataclass."""

    def test_tweet_result_success(self):
        """TweetResult success case."""
        result = TweetResult(tweet_id="123", text="Hello", success=True)
        assert result.success is True
        assert result.tweet_id == "123"
        assert result.error is None

    def test_tweet_result_failure(self):
        """TweetResult failure case."""
        result = TweetResult(
            tweet_id=None, text="Hello", success=False, error="Rate limit exceeded"
        )
        assert result.success is False
        assert result.tweet_id is None
        assert result.error == "Rate limit exceeded"


class TestThreadResult:
    """Tests for ThreadResult dataclass."""

    def test_thread_result_success(self):
        """ThreadResult success case."""
        result = ThreadResult(
            intro_tweet_id="123",
            tweet_results=[],
            success=True,
            message="Posted 11 tweets",
        )
        assert result.success is True
        assert result.intro_tweet_id == "123"

    def test_thread_result_failure(self):
        """ThreadResult failure case."""
        result = ThreadResult(
            intro_tweet_id=None,
            tweet_results=[],
            success=False,
            message="Failed to post intro",
        )
        assert result.success is False
        assert result.intro_tweet_id is None
