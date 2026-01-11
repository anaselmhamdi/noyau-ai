"""Freesound API client for fetching royalty-free background music."""

from dataclasses import dataclass
from pathlib import Path

import httpx

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

FREESOUND_API_BASE = "https://freesound.org/apiv2"


@dataclass
class MusicTrack:
    """A music track from Freesound."""

    id: int
    name: str
    duration: float  # seconds
    url: str
    preview_url: str
    tags: list[str]
    license: str


# Topic to music search query mapping
TOPIC_MUSIC_MAP: dict[str, list[str]] = {
    "dev": ["electronic ambient", "technology background", "corporate ambient"],
    "security": ["dark ambient", "tension background", "suspense"],
    "ai": ["futuristic ambient", "electronic background", "synth pad"],
    "oss": ["upbeat background", "inspiring ambient", "positive corporate"],
    "general": ["corporate background", "ambient music", "background loop"],
}


class FreesoundMusicClient:
    """Client for Freesound API."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
    ):
        settings = get_settings()
        self.client_id = client_id or settings.freesound_client_id
        self.client_secret = client_secret or settings.freesound_client_secret

        if not self.client_secret:
            logger.warning("freesound_credentials_not_set")

    async def search_music(
        self,
        query: str,
        min_duration: int = 30,
        max_duration: int = 180,
        page_size: int = 5,
    ) -> list[MusicTrack]:
        """
        Search for music tracks.

        Args:
            query: Search query (e.g., "ambient background")
            min_duration: Minimum duration in seconds
            max_duration: Maximum duration in seconds
            page_size: Number of results

        Returns:
            List of MusicTrack objects
        """
        if not self.client_secret:
            logger.warning("freesound_search_skipped_no_credentials")
            return []

        async with httpx.AsyncClient() as client:
            try:
                # Filter by duration and look for music-like sounds
                filter_str = f"duration:[{min_duration} TO {max_duration}]"

                response = await client.get(
                    f"{FREESOUND_API_BASE}/search/text/",
                    params={
                        "token": self.client_secret,  # Client secret used as API token
                        "query": query,
                        "filter": filter_str,
                        "fields": "id,name,duration,url,previews,tags,license",
                        "page_size": page_size,
                        "sort": "rating_desc",
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                tracks = []
                for hit in data.get("results", []):
                    previews = hit.get("previews", {})
                    # Prefer HQ MP3, fallback to LQ
                    preview_url = previews.get("preview-hq-mp3", previews.get("preview-lq-mp3", ""))
                    if not preview_url:
                        continue

                    tracks.append(
                        MusicTrack(
                            id=hit["id"],
                            name=hit.get("name", f"Track {hit['id']}"),
                            duration=hit.get("duration", 60),
                            url=hit.get("url", ""),
                            preview_url=preview_url,
                            tags=hit.get("tags", []),
                            license=hit.get("license", ""),
                        )
                    )

                logger.bind(query=query, count=len(tracks)).info("freesound_music_search_complete")
                return tracks

            except httpx.HTTPStatusError as e:
                logger.bind(query=query, status=e.response.status_code).error(
                    "freesound_music_search_http_error"
                )
                return []
            except Exception as e:
                logger.bind(query=query, error=str(e)).error("freesound_music_search_error")
                return []

    async def download_track(
        self,
        track: MusicTrack,
        output_path: Path,
    ) -> Path | None:
        """
        Download a music track preview.

        Args:
            track: MusicTrack to download
            output_path: Path to save the audio file

        Returns:
            Path to downloaded file, or None if failed
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    track.preview_url,
                    timeout=60.0,
                    follow_redirects=True,
                )
                response.raise_for_status()

                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(response.content)

                logger.bind(track_id=track.id, path=str(output_path)).info(
                    "freesound_music_downloaded"
                )
                return output_path

            except Exception as e:
                logger.bind(track_id=track.id, error=str(e)).error("freesound_music_download_error")
                return None


async def fetch_background_music(
    topic: str,
    duration_needed: float,
    output_dir: Path,
    client: FreesoundMusicClient | None = None,
) -> Path | None:
    """
    Fetch background music appropriate for a topic.

    Args:
        topic: Content topic (dev, security, ai, oss, general)
        duration_needed: Duration needed in seconds
        output_dir: Directory to save downloaded music
        client: Optional FreesoundMusicClient instance

    Returns:
        Path to downloaded music file, or None if unavailable
    """
    client = client or FreesoundMusicClient()

    # Get music queries for this topic
    queries = TOPIC_MUSIC_MAP.get(topic, TOPIC_MUSIC_MAP["general"])

    for query in queries:
        tracks = await client.search_music(
            query=query,
            min_duration=int(duration_needed * 0.5),  # Allow shorter (we'll loop)
            max_duration=int(duration_needed * 3),  # Allow longer (we'll trim)
            page_size=5,
        )

        if tracks:
            # Pick the first suitable track
            track = tracks[0]
            output_path = output_dir / f"background_{track.id}.mp3"
            downloaded = await client.download_track(track, output_path)

            if downloaded:
                logger.bind(
                    topic=topic,
                    query=query,
                    track_name=track.name,
                    track_license=track.license,
                ).info("background_music_fetched")
                return downloaded

    logger.bind(topic=topic).warning("no_background_music_available")
    return None
