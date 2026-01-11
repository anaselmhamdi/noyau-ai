from collections.abc import AsyncIterator
from datetime import UTC, datetime

import aiohttp
import feedparser

from app.config import AppConfig
from app.core.logging import get_logger
from app.ingest.base import BaseFetcher, RawContent
from app.ingest.nitter_auth import NitterTokenManager
from app.ingest.normalizer import clean_html

logger = get_logger(__name__)

# Instances that are self-hosted (use http://)
LOCALHOST_PATTERNS = ("localhost", "127.0.0.1", "nitter:")


class NitterFetcher(BaseFetcher):
    """
    Fetcher for X/Twitter content via Nitter RSS feeds.

    Uses public Nitter instances to fetch tweets without Twitter API.
    Falls back through multiple instances if one is unavailable.
    """

    source_name = "x"

    def __init__(
        self,
        accounts: list[dict[str, str]],
        instances: list[str],
        timeout_seconds: int = 10,
        max_retries: int = 3,
    ) -> None:
        """
        Initialize Nitter fetcher.

        Args:
            accounts: List of account configs with 'username' and 'name' keys
            instances: List of Nitter instance hostnames
            timeout_seconds: Request timeout
            max_retries: Max retries per account
        """
        self.accounts = accounts
        self.instances = instances
        self.timeout = timeout_seconds
        self.max_retries = max_retries

    async def fetch(self) -> AsyncIterator[RawContent]:
        """Fetch tweets from all configured X accounts via Nitter."""
        # Check if tokens need refresh before fetching
        await self._ensure_valid_tokens()

        async with aiohttp.ClientSession() as session:
            for account in self.accounts:
                username = account.get("username", "")
                display_name = account.get("name", username)

                if not username:
                    continue

                try:
                    async for item in self._fetch_account(session, username, display_name):
                        yield item
                except Exception as e:
                    logger.bind(username=username, error=str(e)).error("nitter_account_error")

    async def _ensure_valid_tokens(self) -> None:
        """Check token health and refresh if needed."""
        # Find a reachable self-hosted instance for health check
        # Prefer localhost (works outside Docker) over Docker hostname
        local_instances = [
            instance
            for instance in self.instances
            if any(pattern in instance for pattern in LOCALHOST_PATTERNS)
        ]

        # Sort to prefer localhost over docker hostname
        local_instances.sort(key=lambda x: 0 if "localhost" in x else 1)

        if not local_instances:
            # No self-hosted instance, skip health check
            return

        manager = NitterTokenManager()

        # Quick check if we have sessions
        sessions = manager.get_sessions()
        if not sessions:
            logger.warning(
                "nitter_no_sessions", hint="Run: python -m app.jobs.ingest refresh-tokens"
            )
            if manager.refresh_token():
                logger.info("nitter_tokens_auto_refreshed")
            return

        # Try each local instance for health check
        for instance in local_instances:
            nitter_url = f"http://{instance}"
            try:
                is_healthy = await manager.check_token_health(nitter_url)
                if is_healthy:
                    return  # Tokens are good
                # Tokens are unhealthy, try to refresh
                logger.info("nitter_tokens_stale, attempting refresh")
                if manager.refresh_token():
                    logger.info("nitter_tokens_refreshed")
                else:
                    logger.warning("nitter_token_refresh_failed")
                return
            except Exception as e:
                # Instance not reachable, try next one
                logger.debug("nitter_health_check_error", instance=instance, error=str(e))
                continue

    async def _fetch_account(
        self,
        session: aiohttp.ClientSession,
        username: str,
        display_name: str,
    ) -> AsyncIterator[RawContent]:
        """Fetch tweets from a single account, trying multiple Nitter instances."""
        for instance in self.instances:
            # Use http for localhost/docker instances, https for public
            protocol = "http" if any(p in instance for p in LOCALHOST_PATTERNS) else "https"
            feed_url = f"{protocol}://{instance}/{username}/rss"

            try:
                async with session.get(
                    feed_url,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; NoyauAI/1.0)",
                    },
                ) as response:
                    if response.status != 200:
                        logger.bind(
                            instance=instance, username=username, status=response.status
                        ).debug("nitter_instance_failed")
                        continue

                    content = await response.text()
                    feed = feedparser.parse(content)

                    if not feed.entries:
                        continue

                    logger.bind(instance=instance, username=username, count=len(feed.entries)).info(
                        "nitter_fetch_success"
                    )

                    for entry in feed.entries:
                        item = self._parse_entry(entry, username, display_name)
                        if item:
                            yield item

                    # Success - don't try other instances
                    return

            except TimeoutError:
                logger.bind(instance=instance, username=username).debug("nitter_timeout")
            except aiohttp.ClientError as e:
                logger.bind(instance=instance, username=username, error=str(e)).debug(
                    "nitter_client_error"
                )

        logger.bind(username=username).warning("nitter_all_instances_failed")

    def _parse_entry(
        self,
        entry: dict,
        username: str,
        display_name: str,
    ) -> RawContent | None:
        """Parse a Nitter RSS entry into RawContent."""
        # Get URL (tweet link)
        url = entry.get("link")
        if not url:
            return None

        # Convert Nitter URL to Twitter URL
        # Nitter: http://localhost/user/status/123#m
        # Twitter: https://twitter.com/user/status/123
        if "/status/" in url:
            parts = url.split("/")
            status_idx = parts.index("status")
            tweet_id = parts[status_idx + 1] if len(parts) > status_idx + 1 else None
            if tweet_id:
                # Remove fragment (#m) if present
                tweet_id = tweet_id.split("#")[0]
                url = f"https://twitter.com/{username}/status/{tweet_id}"

        # Get content
        text = entry.get("title", "")
        if entry.get("summary"):
            text = clean_html(entry.summary)

        # Extract title (first line or truncated text)
        title_text = text.split("\n")[0] if "\n" in text else text
        if len(title_text) > 100:
            title_text = title_text[:97] + "..."

        # Parse published date
        published = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                published = datetime(*entry.published_parsed[:6], tzinfo=UTC)
            except Exception:
                pass
        if not published:
            published = datetime.now(UTC)

        # Extract metrics from Nitter (if available)
        # Nitter doesn't reliably provide metrics in RSS
        metrics = {
            "username": username,
            "display_name": display_name,
            "likes": 0,
            "retweets": 0,
            "replies": 0,
        }

        return RawContent(
            source="x",
            source_id=entry.get("id"),
            url=url,
            title=title_text,
            author=f"@{username}",
            published_at=published,
            text=text,
            metrics=metrics,
        )


def create_nitter_fetcher(config: AppConfig) -> NitterFetcher | None:
    """Create Nitter fetcher from config."""
    if not config.seeds.x_accounts:
        return None

    return NitterFetcher(
        accounts=config.seeds.x_accounts,
        instances=config.nitter.instances,
        timeout_seconds=config.nitter.timeout_seconds,
        max_retries=config.nitter.max_retries,
    )
