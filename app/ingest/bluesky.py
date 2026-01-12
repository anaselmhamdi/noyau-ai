from collections.abc import AsyncIterator
from datetime import UTC, datetime

import aiohttp

from app.config import AppConfig
from app.core.logging import get_logger
from app.ingest.base import BaseFetcher, RawContent
from app.ingest.normalizer import truncate_text

logger = get_logger(__name__)

# Bluesky public API - no auth required for public data
BLUESKY_API_BASE = "https://public.api.bsky.app"

# Rate limit: Be respectful
BLUESKY_DELAY = 0.5


class BlueskyFetcher(BaseFetcher):
    """
    Fetcher for Bluesky posts using the public AT Protocol API.

    Uses Bluesky's public API which doesn't require authentication
    for reading public posts.
    """

    source_name = "bluesky"

    def __init__(self, accounts: list[dict[str, str]]) -> None:
        """
        Initialize Bluesky fetcher.

        Args:
            accounts: List of account configs with 'handle' and 'name' keys
        """
        self.accounts = accounts

    async def fetch(self) -> AsyncIterator[RawContent]:
        """Fetch posts from all configured Bluesky accounts."""
        async with aiohttp.ClientSession() as session:
            for account_config in self.accounts:
                handle = account_config.get("handle", "")
                name = account_config.get("name", handle)
                if not handle:
                    continue

                try:
                    async for item in self._fetch_account(session, handle, name):
                        yield item
                except Exception as e:
                    logger.bind(handle=handle, error=str(e)).error("bluesky_account_error")

                # Be nice to Bluesky API
                import asyncio

                await asyncio.sleep(BLUESKY_DELAY)

    async def _fetch_account(
        self,
        session: aiohttp.ClientSession,
        handle: str,
        name: str,
    ) -> AsyncIterator[RawContent]:
        """Fetch posts from a single Bluesky account."""
        # First resolve handle to DID if needed
        did = await self._resolve_handle(session, handle)
        if not did:
            logger.bind(handle=handle).warning("bluesky_handle_resolve_failed")
            return

        # Fetch author feed
        url = f"{BLUESKY_API_BASE}/xrpc/app.bsky.feed.getAuthorFeed"

        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=30),
                headers={
                    "User-Agent": "NoyauAI/1.0 (tech news aggregator)",
                    "Accept": "application/json",
                },
                params={
                    "actor": did,
                    "limit": 30,
                    "filter": "posts_no_replies",
                },
            ) as response:
                if response.status == 429:
                    logger.bind(handle=handle).warning("bluesky_rate_limited")
                    return

                if response.status != 200:
                    logger.bind(handle=handle, status=response.status).warning("bluesky_http_error")
                    return

                data = await response.json()
                feed = data.get("feed", [])

                logger.bind(handle=handle, count=len(feed)).info("bluesky_fetch_success")

                for feed_item in feed:
                    post = feed_item.get("post", {})
                    item = self._parse_post(post, handle, name)
                    if item:
                        yield item

        except aiohttp.ClientError as e:
            logger.bind(handle=handle, error=str(e)).error("bluesky_fetch_error")

    async def _resolve_handle(
        self,
        session: aiohttp.ClientSession,
        handle: str,
    ) -> str | None:
        """Resolve a handle to a DID."""
        # If it's already a DID, return as-is
        if handle.startswith("did:"):
            return handle

        url = f"{BLUESKY_API_BASE}/xrpc/com.atproto.identity.resolveHandle"

        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=10),
                params={"handle": handle},
            ) as response:
                if response.status != 200:
                    return None

                data = await response.json()
                did: str | None = data.get("did")
                return did

        except aiohttp.ClientError:
            return None

    def _parse_post(self, post: dict, handle: str, name: str) -> RawContent | None:
        """Parse a Bluesky post into RawContent."""
        # Get the record (actual post content)
        record = post.get("record", {})
        if not record:
            return None

        # Get URI and convert to web URL
        uri = post.get("uri", "")
        if not uri:
            return None

        # URI format: at://did:plc:xxx/app.bsky.feed.post/yyy
        # Convert to: https://bsky.app/profile/handle/post/yyy
        parts = uri.split("/")
        if len(parts) < 5:
            return None
        post_id = parts[-1]
        web_url = f"https://bsky.app/profile/{handle}/post/{post_id}"

        # Get text content
        text = record.get("text", "")
        if not text:
            return None

        text = truncate_text(text)

        # Use text as title (first line or truncated)
        title_text = text.split("\n")[0]
        if len(title_text) > 200:
            title_text = title_text[:197] + "..."
        title = f"{name}: {title_text}"

        # Parse created date
        created_at = record.get("createdAt", "")
        try:
            # ISO format: 2024-01-15T12:00:00.000Z
            published = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            published = datetime.now(UTC)

        # Get metrics
        like_count = post.get("likeCount", 0)
        repost_count = post.get("repostCount", 0)
        reply_count = post.get("replyCount", 0)

        # Check for embedded content (links, images, etc.)
        embed = record.get("embed", {})
        embed_type = embed.get("$type", "")
        external_url = None

        if embed_type == "app.bsky.embed.external":
            external = embed.get("external", {})
            external_url = external.get("uri")

        return RawContent(
            source="bluesky",
            source_id=post_id,
            url=web_url,
            title=title,
            author=f"@{handle}",
            published_at=published,
            text=text,
            metrics={
                "handle": handle,
                "likes": like_count,
                "reposts": repost_count,
                "replies": reply_count,
                "external_url": external_url,
            },
        )


def create_bluesky_fetcher(config: AppConfig) -> BlueskyFetcher | None:
    """Create Bluesky fetcher from config."""
    if not config.seeds.bluesky_accounts:
        return None

    return BlueskyFetcher(config.seeds.bluesky_accounts)
