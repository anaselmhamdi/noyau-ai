from collections.abc import AsyncIterator
from datetime import UTC, datetime

import aiohttp

from app.config import AppConfig
from app.core.logging import get_logger
from app.ingest.base import BaseFetcher, RawContent
from app.ingest.normalizer import truncate_text

logger = get_logger(__name__)

# Reddit JSON API rate limit: Be nice, no more than 1 req/sec
REDDIT_DELAY = 1.0


class RedditFetcher(BaseFetcher):
    """
    Fetcher for Reddit posts using the JSON API.

    Uses Reddit's public JSON API (no auth required for public subreddits).
    Appends .json to subreddit URLs to get JSON data.
    """

    source_name = "reddit"

    def __init__(self, subreddits: list[dict[str, str]]) -> None:
        """
        Initialize Reddit fetcher.

        Args:
            subreddits: List of subreddit configs with 'name' key
        """
        self.subreddits = subreddits

    async def fetch(self) -> AsyncIterator[RawContent]:
        """Fetch posts from all configured subreddits."""
        async with aiohttp.ClientSession() as session:
            for subreddit_config in self.subreddits:
                subreddit = subreddit_config.get("name", "")
                if not subreddit:
                    continue

                try:
                    async for item in self._fetch_subreddit(session, subreddit):
                        yield item
                except Exception as e:
                    logger.bind(subreddit=subreddit, error=str(e)).error("reddit_subreddit_error")

                # Be nice to Reddit API
                import asyncio

                await asyncio.sleep(REDDIT_DELAY)

    async def _fetch_subreddit(
        self,
        session: aiohttp.ClientSession,
        subreddit: str,
    ) -> AsyncIterator[RawContent]:
        """Fetch posts from a single subreddit."""
        url = f"https://www.reddit.com/r/{subreddit}/hot.json"

        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=30),
                headers={
                    "User-Agent": "NoyauAI/1.0 (tech news aggregator)",
                },
                params={"limit": 25},
            ) as response:
                if response.status == 429:
                    logger.bind(subreddit=subreddit).warning("reddit_rate_limited")
                    return

                if response.status != 200:
                    logger.bind(subreddit=subreddit, status=response.status).warning(
                        "reddit_http_error"
                    )
                    return

                data = await response.json()
                posts = data.get("data", {}).get("children", [])

                logger.bind(subreddit=subreddit, count=len(posts)).info("reddit_fetch_success")

                for post in posts:
                    item = self._parse_post(post.get("data", {}), subreddit)
                    if item:
                        yield item

        except aiohttp.ClientError as e:
            logger.bind(subreddit=subreddit, error=str(e)).error("reddit_fetch_error")

    def _parse_post(self, post: dict, subreddit: str) -> RawContent | None:
        """Parse a Reddit post into RawContent."""
        # Skip stickied posts and self-promotional posts
        if post.get("stickied"):
            return None

        # Get URL
        permalink = post.get("permalink")
        if not permalink:
            return None
        url = f"https://www.reddit.com{permalink}"

        # Get title
        title = post.get("title", "")
        if not title:
            return None

        # Get external link if it's a link post
        external_url = post.get("url", "")
        is_self_post = post.get("is_self", False)

        # Get content
        text = ""
        if is_self_post:
            text = post.get("selftext", "")
        else:
            text = f"Link: {external_url}"

        text = truncate_text(text)

        # Parse published date
        created_utc = post.get("created_utc", 0)
        published = datetime.fromtimestamp(created_utc, tz=UTC)

        # Get metrics
        upvotes = post.get("ups", 0) or post.get("score", 0)
        comments = post.get("num_comments", 0)

        return RawContent(
            source="reddit",
            source_id=post.get("id"),
            url=url,
            title=title,
            author=f"u/{post.get('author', 'unknown')}",
            published_at=published,
            text=text,
            metrics={
                "subreddit": subreddit,
                "upvotes": upvotes,
                "comments": comments,
                "upvote_ratio": post.get("upvote_ratio", 0),
                "external_url": external_url if not is_self_post else None,
            },
        )


def create_reddit_fetcher(config: AppConfig) -> RedditFetcher | None:
    """Create Reddit fetcher from config."""
    if not config.seeds.reddit_subreddits:
        return None

    return RedditFetcher(config.seeds.reddit_subreddits)
