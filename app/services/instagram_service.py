"""
Instagram service for posting daily digest videos as Reels via Instagram Graph API.

Uses Facebook's Graph API to publish Reels to Instagram Business/Creator accounts.
Videos must be hosted at a public URL (S3/R2).

API Docs: https://developers.facebook.com/docs/instagram-api/guides/content-publishing
"""

import asyncio
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

# Instagram Graph API endpoints
GRAPH_API_BASE = "https://graph.facebook.com/v18.0"


@dataclass
class InstagramPostResult:
    """Result of posting a Reel to Instagram."""

    media_id: str | None
    success: bool
    error: str | None = None


@dataclass
class InstagramUploadResult:
    """Result of uploading videos to Instagram."""

    results: list[InstagramPostResult]
    success: bool
    message: str


async def _create_media_container(
    client: httpx.AsyncClient,
    account_id: str,
    access_token: str,
    video_url: str,
    caption: str,
) -> tuple[str | None, str | None]:
    """
    Create a media container for a Reel.

    Args:
        client: Async HTTP client
        account_id: Instagram Business Account ID
        access_token: Valid access token
        video_url: Public URL of the video
        caption: Reel caption

    Returns:
        Tuple of (creation_id, error)
    """
    url = f"{GRAPH_API_BASE}/{account_id}/media"

    params = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": access_token,
    }

    try:
        resp = await client.post(url, params=params)
        data = resp.json()

        if resp.status_code == 200 and "id" in data:
            return data["id"], None
        else:
            error = data.get("error", {}).get("message", "Unknown error")
            return None, error

    except Exception as e:
        return None, str(e)


async def _check_container_status(
    client: httpx.AsyncClient,
    creation_id: str,
    access_token: str,
) -> tuple[str, str | None]:
    """
    Check the status of a media container.

    Args:
        client: Async HTTP client
        creation_id: Media container ID
        access_token: Valid access token

    Returns:
        Tuple of (status_code, error_message)
        status_code: EXPIRED, ERROR, FINISHED, IN_PROGRESS, PUBLISHED
    """
    url = f"{GRAPH_API_BASE}/{creation_id}"

    params = {
        "fields": "status_code,status",
        "access_token": access_token,
    }

    try:
        resp = await client.get(url, params=params)
        data = resp.json()

        if resp.status_code == 200:
            status_code = data.get("status_code", "UNKNOWN")
            status = data.get("status", {})
            error = status.get("error_message") if isinstance(status, dict) else None
            return status_code, error
        else:
            error = data.get("error", {}).get("message", "Unknown error")
            return "ERROR", error

    except Exception as e:
        return "ERROR", str(e)


async def _wait_for_container_ready(
    client: httpx.AsyncClient,
    creation_id: str,
    access_token: str,
    max_attempts: int = 30,
    poll_interval: int = 5,
) -> tuple[bool, str | None]:
    """
    Poll until media container is ready for publishing.

    Args:
        client: Async HTTP client
        creation_id: Media container ID
        access_token: Valid access token
        max_attempts: Maximum polling attempts
        poll_interval: Seconds between polls

    Returns:
        Tuple of (is_ready, error_message)
    """
    for attempt in range(max_attempts):
        status_code, error = await _check_container_status(client, creation_id, access_token)

        if status_code == "FINISHED":
            return True, None
        elif status_code in ("ERROR", "EXPIRED"):
            return False, error or f"Container status: {status_code}"
        elif status_code == "IN_PROGRESS":
            logger.bind(attempt=attempt, status=status_code).debug("instagram_container_processing")
            await asyncio.sleep(poll_interval)
        else:
            # Unknown status, wait and retry
            await asyncio.sleep(poll_interval)

    return False, "Timeout waiting for container to be ready"


async def _publish_media(
    client: httpx.AsyncClient,
    account_id: str,
    access_token: str,
    creation_id: str,
) -> tuple[str | None, str | None]:
    """
    Publish a media container as a Reel.

    Args:
        client: Async HTTP client
        account_id: Instagram Business Account ID
        access_token: Valid access token
        creation_id: Media container ID

    Returns:
        Tuple of (media_id, error)
    """
    url = f"{GRAPH_API_BASE}/{account_id}/media_publish"

    params = {
        "creation_id": creation_id,
        "access_token": access_token,
    }

    try:
        resp = await client.post(url, params=params)
        data = resp.json()

        if resp.status_code == 200 and "id" in data:
            return data["id"], None
        else:
            error = data.get("error", {}).get("message", "Unknown error")
            return None, error

    except Exception as e:
        return None, str(e)


def build_reel_caption(item: dict[str, Any], rank: int) -> str:
    """
    Build an Instagram Reel caption from an issue item.

    Args:
        item: Issue item with headline, teaser, etc.
        rank: Story rank (1-10)

    Returns:
        Formatted caption for Instagram (max 2200 chars)
    """
    config = get_config()

    headline = item.get("headline", "")
    teaser = item.get("teaser", "")

    # Build caption
    caption = f"{headline}\n\n{teaser}"

    # Add hashtags if enabled
    if config.instagram.include_hashtags:
        hashtags = config.instagram.default_hashtags
        hashtag_str = " ".join(f"#{tag}" for tag in hashtags)
        caption = f"{caption}\n\n{hashtag_str}"

    # Add CTA
    caption = f"{caption}\n\nMore signal, less noise: noyau.news"

    # Instagram caption limit is 2200 chars
    if len(caption) > 2200:
        caption = caption[:2197] + "..."

    return caption


async def post_instagram_reel(
    video_url: str,
    item: dict[str, Any],
    rank: int,
) -> InstagramPostResult:
    """
    Post a single video as an Instagram Reel.

    Args:
        video_url: Public URL of the video
        item: Issue item for caption
        rank: Story rank

    Returns:
        InstagramPostResult
    """
    config = get_config()

    if not config.instagram.access_token or not config.instagram.business_account_id:
        return InstagramPostResult(
            media_id=None,
            success=False,
            error="Instagram credentials not configured",
        )

    caption = build_reel_caption(item, rank)

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Step 1: Create media container
        logger.bind(rank=rank).info("instagram_creating_container")
        creation_id, error = await _create_media_container(
            client=client,
            account_id=config.instagram.business_account_id,
            access_token=config.instagram.access_token,
            video_url=video_url,
            caption=caption,
        )

        if not creation_id:
            return InstagramPostResult(
                media_id=None,
                success=False,
                error=f"Failed to create container: {error}",
            )

        # Step 2: Wait for container to be ready
        logger.bind(rank=rank, creation_id=creation_id).info("instagram_waiting_for_container")
        is_ready, error = await _wait_for_container_ready(
            client=client,
            creation_id=creation_id,
            access_token=config.instagram.access_token,
        )

        if not is_ready:
            return InstagramPostResult(
                media_id=None,
                success=False,
                error=f"Container not ready: {error}",
            )

        # Step 3: Publish
        logger.bind(rank=rank).info("instagram_publishing_reel")
        media_id, error = await _publish_media(
            client=client,
            account_id=config.instagram.business_account_id,
            access_token=config.instagram.access_token,
            creation_id=creation_id,
        )

        if media_id:
            return InstagramPostResult(
                media_id=media_id,
                success=True,
            )
        else:
            return InstagramPostResult(
                media_id=None,
                success=False,
                error=f"Failed to publish: {error}",
            )


async def send_instagram_reels(
    issue_date: date,
    videos: list[dict[str, Any]],
    items: list[dict[str, Any]],
) -> InstagramUploadResult:
    """
    Post daily digest videos as Instagram Reels.

    Args:
        issue_date: Date of the issue
        videos: List of video results with s3_url
        items: List of issue items for captions

    Returns:
        InstagramUploadResult with success status
    """
    config = get_config()

    # Check if Instagram is enabled
    if not config.instagram.enabled:
        logger.debug("instagram_disabled")
        return InstagramUploadResult(
            results=[],
            success=False,
            message="Instagram posting is disabled",
        )

    # Check for credentials
    if not config.instagram.business_account_id:
        logger.warning("instagram_credentials_not_set")
        return InstagramUploadResult(
            results=[],
            success=False,
            message="Instagram credentials not configured",
        )

    results: list[InstagramPostResult] = []

    # Post top video(s)
    videos_to_post = videos[: config.instagram.reels_per_day]

    for i, video in enumerate(videos_to_post):
        video_url = video.get("s3_url")

        if not video_url:
            logger.bind(rank=i + 1).warning("instagram_no_video_url")
            results.append(
                InstagramPostResult(
                    media_id=None,
                    success=False,
                    error="No S3 URL for video",
                )
            )
            continue

        # Match video to corresponding item for caption
        item = items[i] if i < len(items) else {}

        result = await post_instagram_reel(video_url, item, rank=i + 1)
        results.append(result)

        if result.success:
            logger.bind(
                rank=i + 1,
                media_id=result.media_id,
            ).info("instagram_reel_posted")
        else:
            logger.bind(
                rank=i + 1,
                error=result.error,
            ).warning("instagram_reel_post_failed")

    # Count successes
    successful = sum(1 for r in results if r.success)
    total = len(results)

    if successful == total and total > 0:
        return InstagramUploadResult(
            results=results,
            success=True,
            message=f"Posted {total} Reel(s) to Instagram",
        )
    elif successful > 0:
        return InstagramUploadResult(
            results=results,
            success=True,
            message=f"Partial success: {successful}/{total} Reels posted",
        )
    else:
        return InstagramUploadResult(
            results=results,
            success=False,
            message="Failed to post any Reels to Instagram",
        )
