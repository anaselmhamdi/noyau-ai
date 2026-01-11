"""Pexels API client for fetching stock footage."""

from pathlib import Path

import httpx

from app.config import get_settings
from app.core.logging import get_logger
from app.schemas.video import StockVideo, VideoClip
from app.video.config import StockFootageConfig

logger = get_logger(__name__)

PEXELS_API_BASE = "https://api.pexels.com"


class PexelsClient:
    """Client for Pexels stock footage API."""

    def __init__(self, api_key: str | None = None, config: StockFootageConfig | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.pexels_api_key
        self.config = config or StockFootageConfig()

        if not self.api_key:
            logger.warning("pexels_api_key_not_set")

    async def search_videos(
        self,
        keywords: list[str],
        orientation: str | None = None,
        per_page: int | None = None,
    ) -> list[StockVideo]:
        """
        Search for videos matching keywords.

        Args:
            keywords: Search keywords
            orientation: Video orientation (portrait, landscape, square)
            per_page: Number of results to return

        Returns:
            List of matching StockVideo objects
        """
        if not self.api_key:
            logger.warning("pexels_search_skipped_no_api_key")
            return []

        query = " ".join(keywords)
        orientation = orientation or self.config.orientation
        per_page = per_page or self.config.per_page

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{PEXELS_API_BASE}/videos/search",
                    params={
                        "query": query,
                        "orientation": orientation,
                        "size": "medium",
                        "per_page": per_page,
                    },
                    headers={"Authorization": self.api_key},
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                videos = []
                for video in data.get("videos", []):
                    videos.append(
                        StockVideo(
                            id=video["id"],
                            duration=video["duration"],
                            width=video["width"],
                            height=video["height"],
                            url=video["url"],
                            video_files=video.get("video_files", []),
                            user=video.get("user", {}).get("name", "Unknown"),
                        )
                    )

                logger.bind(query=query, count=len(videos)).info("pexels_search_complete")
                return videos

            except httpx.HTTPStatusError as e:
                logger.bind(query=query, status=e.response.status_code).error(
                    "pexels_search_http_error"
                )
                return []
            except Exception as e:
                logger.bind(query=query, error=str(e)).error("pexels_search_error")
                return []

    async def search_with_fallback(
        self,
        keywords: list[str],
        fallback_queries: list[str] | None = None,
    ) -> list[StockVideo]:
        """
        Search for videos with fallback to generic queries.

        Args:
            keywords: Primary search keywords
            fallback_queries: Fallback queries if primary fails

        Returns:
            List of StockVideo objects
        """
        fallback_queries = fallback_queries or self.config.fallback_queries

        # Try primary keywords
        videos = await self.search_videos(keywords)
        if videos:
            return videos

        # Try individual keywords
        for keyword in keywords[:3]:  # Try top 3 keywords
            videos = await self.search_videos([keyword])
            if videos:
                logger.bind(fallback_keyword=keyword).info("pexels_fallback_keyword_used")
                return videos

        # Try generic fallbacks
        for fallback in fallback_queries:
            videos = await self.search_videos([fallback])
            if videos:
                logger.bind(fallback_query=fallback).info("pexels_fallback_generic_used")
                return videos

        logger.warning("pexels_no_videos_found_after_fallbacks")
        return []

    async def download_video(
        self,
        video: StockVideo,
        output_path: Path,
        quality: str = "hd",
    ) -> Path | None:
        """
        Download a video file from Pexels.

        Args:
            video: StockVideo to download
            output_path: Path to save the video
            quality: Preferred quality (hd, sd)

        Returns:
            Path to downloaded file, or None if download failed
        """
        # Find the best matching video file
        video_file = None
        for vf in video.video_files:
            if vf.get("quality") == quality:
                video_file = vf
                break
        if not video_file and video.video_files:
            video_file = video.video_files[0]

        if not video_file:
            logger.bind(video_id=video.id).warning("pexels_no_video_file_found")
            return None

        download_url = video_file.get("link")
        if not download_url:
            logger.bind(video_id=video.id).warning("pexels_no_download_url")
            return None

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(download_url, timeout=120.0, follow_redirects=True)
                response.raise_for_status()

                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(response.content)

                logger.bind(video_id=video.id, path=str(output_path)).info(
                    "pexels_video_downloaded"
                )
                return output_path

            except Exception as e:
                logger.bind(video_id=video.id, error=str(e)).error("pexels_video_download_error")
                return None


async def fetch_clips_for_script(
    keywords: list[str],
    duration_needed: float,
    output_dir: Path,
    client: PexelsClient | None = None,
) -> list[VideoClip]:
    """
    Fetch and download video clips for a script.

    Args:
        keywords: Keywords for stock footage search
        duration_needed: Total duration needed in seconds
        output_dir: Directory to save downloaded clips
        client: Optional PexelsClient instance

    Returns:
        List of VideoClip objects with local paths
    """
    client = client or PexelsClient()
    videos = await client.search_with_fallback(keywords)

    if not videos:
        logger.warning("no_stock_footage_available")
        return []

    clips = []
    total_duration = 0.0
    clip_index = 0

    for video in videos:
        if total_duration >= duration_needed:
            break

        output_path = output_dir / f"clip_{clip_index}_{video.id}.mp4"
        downloaded_path = await client.download_video(video, output_path)

        if downloaded_path:
            clip_duration = min(video.duration, duration_needed - total_duration)
            clips.append(
                VideoClip(
                    path=str(downloaded_path),
                    start_time=0,  # Will be set during composition
                    duration=clip_duration,
                )
            )
            total_duration += clip_duration
            clip_index += 1

    logger.bind(clips=len(clips), total_duration=total_duration).info("stock_footage_clips_fetched")
    return clips
