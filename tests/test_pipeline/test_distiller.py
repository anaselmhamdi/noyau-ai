"""Tests for LLM distillation."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.pipeline.distiller import distill_cluster, format_cluster_input
from app.schemas.llm import ClusterDistillOutput

pytestmark = pytest.mark.asyncio


class TestFormatClusterInput:
    """Tests for cluster input formatting."""

    def test_formats_items_correctly(self, make_content_item):
        """Should format items for LLM input."""
        items = [
            make_content_item(title="Article 1", url="https://example.com/1"),
            make_content_item(title="Article 2", url="https://example.com/2"),
        ]

        result = format_cluster_input("test-identity", items, "dev")

        assert result.canonical_identity == "test-identity"
        assert result.dominant_topic == "dev"
        assert len(result.items) == 2
        assert result.items[0].title == "Article 1"
        assert result.items[0].url == "https://example.com/1"

    def test_limits_to_five_items(self, make_content_item):
        """Should limit items to 5 for context window."""
        items = [
            make_content_item(title=f"Article {i}", url=f"https://example.com/{i}")
            for i in range(10)
        ]

        result = format_cluster_input("test", items, "dev")

        assert len(result.items) == 5

    def test_truncates_text_excerpt(self, make_content_item):
        """Should truncate long text excerpts."""
        items = [
            make_content_item(title="Title", url="https://example.com", text="x" * 1000),
        ]

        result = format_cluster_input("test", items, "dev")

        # Should be truncated to 500 chars
        assert len(result.items[0].text_excerpt) <= 500


class TestDistillCluster:
    """Tests for cluster distillation."""

    async def test_distill_returns_structured_output(self, make_content_item):
        """Should return ClusterDistillOutput from LLM."""
        items = [
            make_content_item(title="Python 3.13 Released", url="https://python.org/release"),
        ]

        mock_client = AsyncMock()
        mock_parsed = ClusterDistillOutput(
            headline="Python 3.13 Released with Major Performance Boost",
            teaser="The latest Python version brings significant improvements.",
            takeaway="Upgrade your projects to benefit from 15% faster execution.",
            why_care="Directly impacts your development workflow.",
            bullets=[
                "New JIT compiler for numeric workloads",
                "Improved error messages for easier debugging",
            ],
            citations=[
                {"url": "https://python.org/release", "label": "Python.org"},
            ],
            confidence="high",
        )

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.parsed = mock_parsed
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        mock_client.beta.chat.completions.parse = AsyncMock(return_value=mock_response)

        result = await distill_cluster(
            identity="https://python.org",
            items=items,
            client=mock_client,
            dominant_topic="oss",
        )

        assert result is not None
        assert result.output.headline == "Python 3.13 Released with Major Performance Boost"
        assert result.output.confidence == "high"
        assert len(result.output.bullets) == 2
        assert len(result.output.citations) == 1

    async def test_distill_returns_none_on_error(self, make_content_item):
        """Should return None on API error."""
        items = [make_content_item(title="Test", url="https://example.com")]

        mock_client = AsyncMock()
        mock_client.beta.chat.completions.parse = AsyncMock(side_effect=Exception("API Error"))

        result = await distill_cluster(
            identity="test",
            items=items,
            client=mock_client,
        )

        assert result is None

    async def test_distill_returns_none_on_empty_response(self, make_content_item):
        """Should return None when LLM returns no parsed content."""
        items = [make_content_item(title="Test", url="https://example.com")]

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.parsed = None
        mock_client.beta.chat.completions.parse = AsyncMock(return_value=mock_response)

        result = await distill_cluster(
            identity="test",
            items=items,
            client=mock_client,
        )

        assert result is None
