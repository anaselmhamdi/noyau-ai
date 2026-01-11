from collections.abc import AsyncIterator
from datetime import UTC, datetime

import aiohttp
import feedparser

from app.config import AppConfig
from app.core.logging import get_logger
from app.ingest.base import BaseFetcher, RawContent
from app.ingest.normalizer import clean_html, truncate_text

logger = get_logger(__name__)


class RSSFetcher(BaseFetcher):
    """Fetcher for RSS and Atom feeds."""

    source_name = "rss"

    def __init__(self, feeds: list[dict[str, str]]) -> None:
        """
        Initialize RSS fetcher.

        Args:
            feeds: List of feed configs with 'url' and 'name' keys
        """
        self.feeds = feeds

    async def fetch(self) -> AsyncIterator[RawContent]:
        """Fetch items from all configured RSS feeds."""
        async with aiohttp.ClientSession() as session:
            for feed_config in self.feeds:
                feed_url = feed_config.get("url", "")
                feed_name = feed_config.get("name", feed_url)

                try:
                    async for item in self._fetch_feed(session, feed_url, feed_name):
                        yield item
                except Exception as e:
                    logger.bind(feed_url=feed_url, error=str(e)).error("rss_feed_error")

    async def _fetch_feed(
        self,
        session: aiohttp.ClientSession,
        feed_url: str,
        feed_name: str,
    ) -> AsyncIterator[RawContent]:
        """Fetch and parse a single RSS feed."""
        try:
            async with session.get(
                feed_url,
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"User-Agent": "NoyauAI/1.0"},
            ) as response:
                if response.status != 200:
                    logger.bind(feed_url=feed_url, status=response.status).warning(
                        "rss_feed_http_error"
                    )
                    return

                content = await response.text()
                feed = feedparser.parse(content)

                for entry in feed.entries:
                    try:
                        item = self._parse_entry(entry, feed_name)
                        if item:
                            yield item
                    except Exception as e:
                        logger.bind(feed_url=feed_url, error=str(e)).warning(
                            "rss_entry_parse_error"
                        )

        except aiohttp.ClientError as e:
            logger.bind(feed_url=feed_url, error=str(e)).error("rss_fetch_error")

    def _parse_entry(self, entry: dict, feed_name: str) -> RawContent | None:
        """Parse a single RSS entry into RawContent."""
        # Get URL
        url = entry.get("link") or entry.get("id")
        if not url:
            return None

        # Get title
        title = entry.get("title", "")
        if not title:
            return None

        # Get published date
        published = None
        for date_field in ["published_parsed", "updated_parsed", "created_parsed"]:
            if hasattr(entry, date_field) and getattr(entry, date_field):
                try:
                    published = datetime(*getattr(entry, date_field)[:6], tzinfo=UTC)  # type: ignore[misc]
                    break
                except Exception as e:
                    logger.debug("rss_date_parsing_failed", field=date_field, error=str(e))
                    continue

        if not published:
            published = datetime.now(UTC)

        # Get content/summary
        text = ""
        if entry.get("content"):
            text = entry.content[0].get("value", "")  # type: ignore[attr-defined]
        elif entry.get("summary"):
            text = entry.summary  # type: ignore[attr-defined]

        text = clean_html(text)
        text = truncate_text(text)

        # Get author
        author = entry.get("author") or entry.get("author_detail", {}).get("name")

        return RawContent(
            source="rss",
            source_id=entry.get("id"),
            url=url,
            title=clean_html(title),
            author=author,
            published_at=published,
            text=text,
            metrics={
                "feed_name": feed_name,
            },
        )


class GitHubReleasesFetcher(BaseFetcher):
    """Fetcher for GitHub releases.atom feeds."""

    source_name = "github"

    def __init__(self, feeds: list[dict[str, str]]) -> None:
        """
        Initialize GitHub releases fetcher.

        Args:
            feeds: List of feed configs with 'url' and 'name' keys
        """
        self.feeds = feeds

    async def fetch(self) -> AsyncIterator[RawContent]:
        """Fetch items from all configured GitHub release feeds."""
        async with aiohttp.ClientSession() as session:
            for feed_config in self.feeds:
                feed_url = feed_config.get("url", "")
                repo_name = feed_config.get("name", feed_url)

                try:
                    async for item in self._fetch_releases(session, feed_url, repo_name):
                        yield item
                except Exception as e:
                    logger.bind(feed_url=feed_url, error=str(e)).error("github_releases_error")

    async def _fetch_releases(
        self,
        session: aiohttp.ClientSession,
        feed_url: str,
        repo_name: str,
    ) -> AsyncIterator[RawContent]:
        """Fetch and parse GitHub releases feed."""
        try:
            async with session.get(
                feed_url,
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"User-Agent": "NoyauAI/1.0"},
            ) as response:
                if response.status != 200:
                    return

                content = await response.text()
                feed = feedparser.parse(content)

                for entry in feed.entries:
                    try:
                        # Extract version from title
                        title = entry.get("title", "")
                        url = entry.get("link", "")

                        if not url:
                            continue

                        # Parse published date
                        published = None
                        if hasattr(entry, "updated_parsed") and entry.updated_parsed:
                            published = datetime(*entry.updated_parsed[:6], tzinfo=UTC)  # type: ignore[misc]
                        if not published:
                            published = datetime.now(UTC)

                        # Get release notes
                        text = ""
                        if entry.get("content"):
                            text = entry.content[0].get("value", "")
                        elif entry.get("summary"):
                            text = entry.summary
                        text = clean_html(text)
                        text = truncate_text(text, 3000)

                        yield RawContent(
                            source="github",
                            source_id=entry.get("id"),
                            url=url,
                            title=f"{repo_name}: {title}" if title else repo_name,
                            author=repo_name,
                            published_at=published,
                            text=text,
                            metrics={
                                "repo": repo_name,
                                "release": True,
                            },
                        )
                    except Exception as e:
                        logger.bind(error=str(e)).warning("github_entry_error")

        except aiohttp.ClientError as e:
            logger.bind(feed_url=feed_url, error=str(e)).error("github_fetch_error")


def create_rss_fetchers(config: AppConfig) -> list[BaseFetcher]:
    """Create RSS and GitHub release fetchers from config."""
    fetchers: list[BaseFetcher] = []

    if config.seeds.rss_feeds:
        fetchers.append(RSSFetcher(config.seeds.rss_feeds))

    if config.seeds.github_release_feeds:
        fetchers.append(GitHubReleasesFetcher(config.seeds.github_release_feeds))

    return fetchers
