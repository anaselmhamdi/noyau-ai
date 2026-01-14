import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import aiohttp
import feedparser

from app.config import AppConfig
from app.core.logging import get_logger
from app.ingest.base import BaseFetcher, RawContent
from app.ingest.normalizer import clean_html, truncate_text

logger = get_logger(__name__)


class YouTubeFetcher(BaseFetcher):
    """
    Fetcher for YouTube videos with transcript support.

    Uses YouTube RSS feeds for video discovery and
    youtube-transcript-api for transcripts.
    """

    source_name = "youtube"

    def __init__(self, channels: list[dict[str, str]]) -> None:
        """
        Initialize YouTube fetcher.

        Args:
            channels: List of channel configs with 'channel_id' and 'name' keys
        """
        self.channels = channels

    async def fetch(self) -> AsyncIterator[RawContent]:
        """Fetch videos from all configured YouTube channels."""
        async with aiohttp.ClientSession() as session:
            for channel in self.channels:
                channel_id = channel.get("channel_id", "")
                channel_name = channel.get("name", channel_id)

                if not channel_id:
                    continue

                try:
                    async for item in self._fetch_channel(session, channel_id, channel_name):
                        yield item
                except Exception as e:
                    logger.bind(channel_id=channel_id, error=str(e)).error("youtube_channel_error")

                await asyncio.sleep(0.5)

    async def _fetch_channel(
        self,
        session: aiohttp.ClientSession,
        channel_id: str,
        channel_name: str,
    ) -> AsyncIterator[RawContent]:
        """Fetch videos from a single YouTube channel."""
        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

        try:
            async with session.get(
                feed_url,
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"User-Agent": "NoyauAI/1.0"},
            ) as response:
                if response.status != 200:
                    logger.bind(channel_id=channel_id, status=response.status).warning(
                        "youtube_http_error"
                    )
                    return

                content = await response.text()
                feed = feedparser.parse(content)

                logger.bind(channel_name=channel_name, count=len(feed.entries)).info(
                    "youtube_fetch_success"
                )

                for entry in feed.entries[:10]:  # Limit to recent videos
                    item = await self._parse_entry(entry, channel_name)
                    if item:
                        yield item

        except aiohttp.ClientError as e:
            logger.bind(channel_id=channel_id, error=str(e)).error("youtube_fetch_error")

    async def _parse_entry(
        self,
        entry: dict,
        channel_name: str,
    ) -> RawContent | None:
        """Parse a YouTube feed entry into RawContent."""
        # Get video ID and URL
        video_id = entry.get("yt_videoid")
        if not video_id:
            # Try to extract from link
            link = entry.get("link", "")
            if "watch?v=" in link:
                video_id = link.split("watch?v=")[1].split("&")[0]

        if not video_id:
            return None

        url = f"https://www.youtube.com/watch?v={video_id}"

        # Get title
        title = entry.get("title", "")
        if not title:
            return None

        # Parse published date
        published = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                published = datetime(*entry.published_parsed[:6], tzinfo=UTC)  # type: ignore[misc]
            except Exception as e:
                logger.debug("youtube_date_parsing_failed", error=str(e))
        if not published:
            published = datetime.now(UTC)

        # Get description from media_group
        description = ""
        if hasattr(entry, "media_group"):
            for media in entry.media_group:
                if hasattr(media, "media_description"):
                    description = media.media_description
                    break
        if not description and entry.get("summary"):
            description = clean_html(entry.summary)  # type: ignore[attr-defined]

        # Try to get transcript
        transcript_text = await self._get_transcript(video_id)

        # Use transcript if available, otherwise description
        text = transcript_text or description
        text = truncate_text(text, 3000)

        # Get view count if available
        views = 0
        if hasattr(entry, "media_statistics"):
            views = int(entry.media_statistics.get("views", 0))

        return RawContent(
            source="youtube",
            source_id=video_id,
            url=url,
            title=f"{channel_name}: {title}",
            author=channel_name,
            published_at=published,
            text=text,
            metrics={
                "channel": channel_name,
                "video_id": video_id,
                "views": views,
                "has_transcript": bool(transcript_text),
            },
        )

    async def _get_transcript(self, video_id: str) -> str | None:
        """
        Get transcript for a YouTube video.

        Uses youtube-transcript-api library.
        Returns None if transcript is unavailable.
        """
        try:
            # Import here to avoid issues if library not installed
            from youtube_transcript_api import YouTubeTranscriptApi
            from youtube_transcript_api._errors import (
                NoTranscriptFound,
                TranscriptsDisabled,
            )

            # Run in executor since it's blocking
            loop = asyncio.get_event_loop()
            transcript_list = await loop.run_in_executor(
                None,
                lambda: YouTubeTranscriptApi.get_transcript(video_id),  # type: ignore[attr-defined]
            )

            # Combine transcript segments
            text_parts = [segment.get("text", "") for segment in transcript_list]
            full_text = " ".join(text_parts)

            return full_text

        except (NoTranscriptFound, TranscriptsDisabled):
            logger.bind(video_id=video_id).debug("youtube_no_transcript")
            return None
        except ImportError:
            logger.warning("youtube_transcript_api_not_installed")
            return None
        except Exception as e:
            logger.bind(video_id=video_id, error=str(e)).debug("youtube_transcript_error")
            return None


def create_youtube_fetcher(config: AppConfig) -> YouTubeFetcher | None:
    """Create YouTube fetcher from config."""
    if not config.seeds.youtube_channels:
        return None

    return YouTubeFetcher(config.seeds.youtube_channels)
