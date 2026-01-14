import asyncio
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import aiohttp

from app.config import AppConfig
from app.core.logging import get_logger
from app.ingest.base import BaseFetcher, RawContent
from app.ingest.normalizer import truncate_text

logger = get_logger(__name__)

# Pattern to match weekly/monthly article compilation posts
# Matches: "Top 7 articles of the week", "Top 10 DEV posts this month", etc.
# Does NOT match: "Top 7 tools", "Top 10 libraries", etc.
COMPILATION_PATTERN = re.compile(
    r"top\s+\d+\s+(\w+\s+)?(articles?|posts?|stories?|reads?)\s+(of\s+the|this|last)\s+(week|month|day)",
    re.IGNORECASE,
)


class DevToFetcher(BaseFetcher):
    """
    Fetcher for dev.to articles using their public API.

    API docs: https://developers.forem.com/api/v0
    """

    source_name = "devto"
    base_url = "https://dev.to/api/articles"

    def __init__(self, tags: list[str]) -> None:
        """
        Initialize dev.to fetcher.

        Args:
            tags: List of tag names to fetch
        """
        self.tags = tags

    async def fetch(self) -> AsyncIterator[RawContent]:
        """Fetch articles from all configured tags."""
        async with aiohttp.ClientSession() as session:
            for tag in self.tags:
                try:
                    async for item in self._fetch_tag(session, tag):
                        yield item
                except Exception as e:
                    logger.bind(tag=tag, error=str(e)).error("devto_tag_error")

                # Be nice to the API
                await asyncio.sleep(0.5)

    async def _fetch_tag(
        self,
        session: aiohttp.ClientSession,
        tag: str,
    ) -> AsyncIterator[RawContent]:
        """Fetch articles for a single tag."""
        try:
            async with session.get(
                self.base_url,
                timeout=aiohttp.ClientTimeout(total=30),
                headers={
                    "User-Agent": "NoyauAI/1.0",
                    "Accept": "application/json",
                },
                params={
                    "tag": tag,
                    "per_page": 20,
                    "state": "fresh",  # Recent articles
                },
            ) as response:
                if response.status != 200:
                    logger.bind(tag=tag, status=response.status).warning("devto_http_error")
                    return

                articles = await response.json()

                logger.bind(tag=tag, count=len(articles)).info("devto_fetch_success")

                for article in articles:
                    item = self._parse_article(article, tag)
                    if item:
                        yield item

        except aiohttp.ClientError as e:
            logger.bind(tag=tag, error=str(e)).error("devto_fetch_error")

    def _parse_article(self, article: dict, tag: str) -> RawContent | None:
        """Parse a dev.to article into RawContent."""
        url = article.get("url")
        if not url:
            return None

        title = article.get("title", "")
        if not title:
            return None

        # Skip weekly/monthly article compilations
        if COMPILATION_PATTERN.search(title):
            logger.bind(title=title).debug("devto_skip_compilation")
            return None

        # Get description/excerpt
        description = article.get("description", "")
        text = truncate_text(description)

        # Parse published date
        published_str = article.get("published_at") or article.get("created_at")
        published = datetime.now(UTC)
        if published_str:
            try:
                # dev.to uses ISO format: 2024-01-15T10:30:00Z
                published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            except Exception:
                pass

        # Get metrics
        reactions = article.get("positive_reactions_count", 0)
        comments = article.get("comments_count", 0)

        # Get author
        user = article.get("user", {})
        author = user.get("username") or user.get("name")

        return RawContent(
            source="devto",
            source_id=str(article.get("id")),
            url=url,
            title=title,
            author=author,
            published_at=published,
            text=text,
            metrics={
                "tag": tag,
                "reactions": reactions,
                "comments": comments,
                "reading_time_minutes": article.get("reading_time_minutes", 0),
            },
        )


def create_devto_fetcher(config: AppConfig) -> DevToFetcher | None:
    """Create dev.to fetcher from config."""
    if not config.seeds.devto_tags:
        return None

    return DevToFetcher(config.seeds.devto_tags)
