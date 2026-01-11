"""YouTube upload functionality using YouTube Data API v3."""

from pathlib import Path
from typing import Protocol

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from app.config import get_settings
from app.core.logging import get_logger
from app.schemas.video import YouTubeMetadata

logger = get_logger(__name__)

# YouTube API configuration
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class YouTubeConfigProtocol(Protocol):
    """Protocol for YouTube configuration."""

    category_id: str
    privacy_status: str
    made_for_kids: bool
    default_language: str
    default_tags: list[str]


class YouTubeUploader:
    """YouTube video uploader using Data API v3."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
        config: YouTubeConfigProtocol | None = None,
    ):
        """
        Initialize YouTube uploader.

        Requires OAuth credentials (client_id, client_secret, refresh_token).
        These can be obtained through the YouTube API OAuth flow.
        """
        settings = get_settings()
        self.client_id = client_id or settings.youtube_client_id
        self.client_secret = client_secret or settings.youtube_client_secret
        self.refresh_token = refresh_token or settings.youtube_refresh_token
        if config is None:
            from app.video.config import YouTubeConfig

            config = YouTubeConfig()
        self.config = config
        self._service = None

    def _is_configured(self) -> bool:
        """Check if YouTube credentials are configured."""
        return bool(self.client_id and self.client_secret and self.refresh_token)

    def _get_service(self):
        """Get authenticated YouTube API service."""
        if self._service:
            return self._service

        if not self._is_configured():
            logger.warning("youtube_credentials_not_configured")
            return None

        try:
            credentials = Credentials(
                token=None,
                refresh_token=self.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.client_id,
                client_secret=self.client_secret,
            )

            self._service = build(
                YOUTUBE_API_SERVICE_NAME,
                YOUTUBE_API_VERSION,
                credentials=credentials,
            )

            return self._service

        except Exception as e:
            logger.bind(error=str(e)).error("youtube_service_initialization_error")
            return None

    async def upload_video(
        self,
        video_path: Path,
        metadata: YouTubeMetadata,
    ) -> tuple[str, str] | None:
        """
        Upload a video to YouTube.

        Args:
            video_path: Path to the video file
            metadata: Video metadata (title, description, tags, etc.)

        Returns:
            Tuple of (video_id, video_url), or None if upload failed
        """
        service = self._get_service()
        if not service:
            return None

        if not video_path.exists():
            logger.bind(path=str(video_path)).error("video_file_not_found")
            return None

        try:
            # Prepare video body
            body = {
                "snippet": {
                    "title": metadata.title,
                    "description": metadata.description,
                    "tags": metadata.tags + self.config.default_tags,
                    "categoryId": metadata.category_id or self.config.category_id,
                    "defaultLanguage": self.config.default_language,
                },
                "status": {
                    "privacyStatus": metadata.privacy_status or self.config.privacy_status,
                    "madeForKids": metadata.made_for_kids,
                    "selfDeclaredMadeForKids": metadata.made_for_kids,
                },
            }

            # Prepare media upload
            media = MediaFileUpload(
                str(video_path),
                mimetype="video/mp4",
                resumable=True,
                chunksize=1024 * 1024,  # 1MB chunks
            )

            # Insert video
            request = service.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            # Execute upload with progress logging
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    logger.bind(progress=progress).debug("youtube_upload_progress")

            video_id = response["id"]
            video_url = f"https://youtube.com/shorts/{video_id}"

            logger.bind(
                video_id=video_id,
                title=metadata.title,
            ).info("youtube_video_uploaded")

            return video_id, video_url

        except Exception as e:
            logger.bind(
                error=str(e),
                title=metadata.title,
            ).error("youtube_upload_error")
            return None

    async def set_thumbnail(
        self,
        video_id: str,
        thumbnail_path: Path,
    ) -> bool:
        """
        Set custom thumbnail for a video.

        Args:
            video_id: YouTube video ID
            thumbnail_path: Path to thumbnail image

        Returns:
            True if successful, False otherwise
        """
        service = self._get_service()
        if not service:
            return False

        if not thumbnail_path.exists():
            logger.bind(path=str(thumbnail_path)).warning("thumbnail_file_not_found")
            return False

        try:
            media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")
            service.thumbnails().set(
                videoId=video_id,
                media_body=media,
            ).execute()

            logger.bind(video_id=video_id).info("youtube_thumbnail_set")
            return True

        except Exception as e:
            logger.bind(video_id=video_id, error=str(e)).error("youtube_thumbnail_error")
            return False


def create_video_metadata(
    headline: str,
    teaser: str,
    topic: str,
    rank: int,
    citations: list[dict] | None = None,
    config: YouTubeConfigProtocol | None = None,
) -> YouTubeMetadata:
    """
    Create YouTube metadata from video content.

    Args:
        headline: Video headline
        teaser: Video teaser/summary
        topic: Topic category
        rank: Rank in daily digest
        citations: List of citation dicts with url and label
        config: YouTube configuration

    Returns:
        YouTubeMetadata object
    """
    if config is None:
        from app.video.config import YouTubeConfig

        config = YouTubeConfig()

    # Format title for Shorts (include hashtag)
    title = f"{headline} #shorts #technews"
    if len(title) > 100:
        title = f"{headline[:85]}... #shorts"

    # Build description
    description_parts = [
        teaser,
        "",
        f"📰 #{rank} story from today's Noyau digest",
        "",
        "🔗 Read full digest: https://noyau.news",
    ]

    if citations:
        description_parts.extend(["", "📚 Sources:"])
        for citation in citations[:5]:
            label = citation.get("label", "Source")
            url = citation.get("url", "")
            if url:
                description_parts.append(f"• {label}: {url}")

    description_parts.extend(
        [
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━",
            "🌐 Website: https://noyau.news",
            "📧 Subscribe for daily tech news",
            "",
            "#technews #programming #developer #noyau",
        ]
    )

    description = "\n".join(description_parts)

    # Generate tags based on topic
    topic_tags = {
        "dev": ["programming", "software development", "coding"],
        "security": ["cybersecurity", "infosec", "vulnerability"],
        "oss": ["open source", "github", "developer tools"],
        "ai": ["artificial intelligence", "machine learning", "AI news"],
        "cloud": ["cloud computing", "devops", "infrastructure"],
        "general": ["technology", "tech industry"],
    }

    tags = ["tech news", "noyau", "developer news"]
    tags.extend(topic_tags.get(topic, topic_tags["general"]))

    return YouTubeMetadata(
        title=title,
        description=description,
        tags=tags,
        privacy_status=config.privacy_status,
        made_for_kids=config.made_for_kids,
    )
