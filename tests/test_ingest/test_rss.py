"""Tests for RSS feed fetching."""

from unittest.mock import AsyncMock, patch

import pytest

from app.ingest.rss import GitHubReleasesFetcher, RSSFetcher

pytestmark = pytest.mark.asyncio


class TestRSSFetcher:
    """Tests for RSS/Atom feed fetcher."""

    @pytest.fixture
    def rss_feed_content(self):
        """Sample RSS feed XML."""
        return """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title>Test Feed</title>
                <link>https://example.com</link>
                <item>
                    <title>Article One</title>
                    <link>https://example.com/article-1</link>
                    <description>Description of article one</description>
                    <pubDate>Wed, 10 Jan 2026 10:00:00 GMT</pubDate>
                    <author>author@example.com</author>
                </item>
                <item>
                    <title>Article Two</title>
                    <link>https://example.com/article-2</link>
                    <description><![CDATA[<p>HTML description</p>]]></description>
                    <pubDate>Wed, 10 Jan 2026 09:00:00 GMT</pubDate>
                </item>
            </channel>
        </rss>
        """

    async def test_fetch_parses_rss_items(self, rss_feed_content):
        """Should parse RSS items correctly."""
        fetcher = RSSFetcher([{"url": "https://example.com/feed", "name": "Test"}])

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value=rss_feed_content)
            mock_get.return_value.__aenter__.return_value = mock_response

            items = []
            async for item in fetcher.fetch():
                items.append(item)

            assert len(items) == 2
            assert items[0].title == "Article One"
            assert items[0].url == "https://example.com/article-1"
            assert items[0].source == "rss"

    async def test_fetch_handles_http_error(self):
        """Should handle HTTP errors gracefully."""
        fetcher = RSSFetcher([{"url": "https://example.com/feed", "name": "Test"}])

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_get.return_value.__aenter__.return_value = mock_response

            items = []
            async for item in fetcher.fetch():
                items.append(item)

            assert len(items) == 0

    async def test_fetch_handles_connection_error(self):
        """Should handle connection errors gracefully."""
        import aiohttp

        fetcher = RSSFetcher([{"url": "https://example.com/feed", "name": "Test"}])

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.side_effect = aiohttp.ClientError("Connection failed")

            items = []
            async for item in fetcher.fetch():
                items.append(item)

            assert len(items) == 0


class TestGitHubReleasesFetcher:
    """Tests for GitHub releases fetcher."""

    @pytest.fixture
    def releases_atom_content(self):
        """Sample GitHub releases Atom feed."""
        return """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <title>Release notes from kubernetes</title>
            <entry>
                <id>tag:github.com,2008:Repository/123/v1.30.0</id>
                <updated>2026-01-10T10:00:00Z</updated>
                <link rel="alternate" type="text/html" href="https://github.com/kubernetes/kubernetes/releases/tag/v1.30.0"/>
                <title>v1.30.0</title>
                <content type="html">Release notes content</content>
            </entry>
        </feed>
        """

    async def test_fetch_parses_releases(self, releases_atom_content):
        """Should parse GitHub releases correctly."""
        fetcher = GitHubReleasesFetcher(
            [
                {
                    "url": "https://github.com/kubernetes/kubernetes/releases.atom",
                    "name": "Kubernetes",
                }
            ]
        )

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value=releases_atom_content)
            mock_get.return_value.__aenter__.return_value = mock_response

            items = []
            async for item in fetcher.fetch():
                items.append(item)

            assert len(items) == 1
            assert "v1.30.0" in items[0].title
            assert items[0].source == "github"
