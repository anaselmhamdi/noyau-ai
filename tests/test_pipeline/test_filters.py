"""Tests for content filtering."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.datetime_utils import utc_now
from app.models.content import ContentItem, ContentSource
from app.pipeline.filters import (
    filter_political_items,
    keyword_filter,
    llm_politics_check,
)

pytestmark = pytest.mark.asyncio


class TestKeywordFilter:
    """Tests for keyword-based politics filter."""

    def test_detects_election_keyword(self):
        """Should detect 'election' keyword."""
        text = "The upcoming presidential election will be important"
        assert keyword_filter(text) is True

    def test_detects_senate_keyword(self):
        """Should detect 'senate' keyword."""
        text = "Senate votes on new legislation"
        assert keyword_filter(text) is True

    def test_case_insensitive(self):
        """Should be case insensitive."""
        text = "ELECTION results announced"
        assert keyword_filter(text) is True

    def test_no_match_for_tech_content(self):
        """Should not match pure tech content."""
        text = "New Python 3.13 release brings performance improvements"
        assert keyword_filter(text) is False

    def test_matches_distributed_systems_election(self):
        """Should match 'election' even in tech context (false positive)."""
        text = "Leader election algorithm in distributed systems"
        # This is a known limitation - LLM check handles false positives
        assert keyword_filter(text) is True


class TestLlmPoliticsCheck:
    """Tests for LLM-based politics validation."""

    async def test_returns_false_for_tech_election(self):
        """Should return false for technical 'election' usage."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not_political"
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        text = "Implementing leader election in Raft consensus"
        result = await llm_politics_check(text, mock_client)

        assert result is False

    async def test_returns_true_for_actual_politics(self):
        """Should return true for political content."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "political"
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        text = "Presidential candidate announces new policy"
        result = await llm_politics_check(text, mock_client)

        assert result is True

    async def test_handles_api_error(self):
        """Should return False on API error (fail open)."""
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))

        text = "Some text"
        result = await llm_politics_check(text, mock_client)

        assert result is False


class TestFilterPoliticalItems:
    """Tests for filtering political items."""

    async def test_keeps_non_political_items(self):
        """Should keep items without political keywords."""
        items = [
            self._make_item("Python 3.13 Released"),
            self._make_item("New Kubernetes Features"),
        ]

        filtered = await filter_political_items(items, client=None)

        assert len(filtered) == 2

    async def test_removes_political_items_keyword_only(self):
        """Should remove items with political keywords (no LLM)."""
        items = [
            self._make_item("Tech News"),
            self._make_item("Senate votes on tech regulation"),
        ]

        with patch("app.pipeline.filters.get_config") as mock_config:
            mock_config.return_value.filters.exclude_politics = True
            mock_config.return_value.filters.politics_keywords = ["senate"]

            filtered = await filter_political_items(items, client=None)

            assert len(filtered) == 1
            assert filtered[0].title == "Tech News"

    async def test_uses_llm_for_edge_cases(self):
        """Should use LLM to validate keyword matches."""
        items = [
            self._make_item("Leader election in distributed systems"),
        ]

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not_political"
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("app.pipeline.filters.get_config") as mock_config:
            mock_config.return_value.filters.exclude_politics = True
            mock_config.return_value.filters.politics_keywords = ["election"]

            filtered = await filter_political_items(items, client=mock_client)

            # Should keep the item because LLM says it's not political
            assert len(filtered) == 1

    def _make_item(self, title: str) -> ContentItem:
        return ContentItem(
            source=ContentSource.RSS,
            url=f"https://example.com/{title.lower().replace(' ', '-')}",
            title=title,
            published_at=utc_now(),
            text="",
        )
