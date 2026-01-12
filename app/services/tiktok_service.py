"""
TikTok service for posting daily digest videos via TikTok Content Posting API.

Uses OAuth 2.0 for authentication. Requires one-time manual auth flow to get
refresh token, then auto-refreshes as needed.

API Docs: https://developers.tiktok.com/doc/content-posting-api-get-started
"""

import asyncio
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

# TikTok API endpoints
TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_REVOKE_URL = "https://open.tiktokapis.com/v2/oauth/revoke/"
TIKTOK_USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"

# Content Posting API endpoints
TIKTOK_POST_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
TIKTOK_POST_STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"


@dataclass
class TikTokTokens:
    """TikTok OAuth tokens."""

    access_token: str
    refresh_token: str
    expires_in: int
    open_id: str


@dataclass
class TikTokPostResult:
    """Result of posting a video to TikTok."""

    publish_id: str | None
    success: bool
    error: str | None = None


@dataclass
class TikTokUploadResult:
    """Result of uploading videos to TikTok."""

    results: list[TikTokPostResult]
    success: bool
    message: str


def build_auth_url(state: str | None = None) -> str:
    """
    Build the TikTok OAuth authorization URL for initial setup.

    Args:
        state: Optional state parameter for CSRF protection

    Returns:
        Authorization URL to redirect user to
    """
    config = get_config()

    params = {
        "client_key": config.tiktok.client_key,
        "response_type": "code",
        "scope": "user.info.basic,video.publish",
        "redirect_uri": config.tiktok.redirect_uri,
    }

    if state:
        params["state"] = state

    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{TIKTOK_AUTH_URL}?{query}"


async def exchange_code_for_tokens(code: str) -> TikTokTokens | None:
    """
    Exchange authorization code for access and refresh tokens.

    Args:
        code: Authorization code from OAuth callback

    Returns:
        TikTokTokens if successful, None otherwise
    """
    config = get_config()

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                TIKTOK_TOKEN_URL,
                data={
                    "client_key": config.tiktok.client_key,
                    "client_secret": config.tiktok.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": config.tiktok.redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if resp.status_code == 200:
                data = resp.json()
                return TikTokTokens(
                    access_token=data["access_token"],
                    refresh_token=data["refresh_token"],
                    expires_in=data["expires_in"],
                    open_id=data["open_id"],
                )
            else:
                logger.bind(
                    status=resp.status_code,
                    response=resp.text[:200],
                ).error("tiktok_token_exchange_failed")
                return None

        except Exception as e:
            logger.bind(error=str(e)).error("tiktok_token_exchange_error")
            return None


async def refresh_access_token() -> str | None:
    """
    Refresh the access token using the stored refresh token.

    Returns:
        New access token if successful, None otherwise
    """
    config = get_config()

    if not config.tiktok.refresh_token:
        logger.warning("tiktok_no_refresh_token")
        return None

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                TIKTOK_TOKEN_URL,
                data={
                    "client_key": config.tiktok.client_key,
                    "client_secret": config.tiktok.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": config.tiktok.refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if resp.status_code == 200:
                data = resp.json()
                # In production, you'd want to persist the new refresh_token
                logger.info("tiktok_token_refreshed")
                return str(data["access_token"])
            else:
                logger.bind(
                    status=resp.status_code,
                    response=resp.text[:200],
                ).error("tiktok_token_refresh_failed")
                return None

        except Exception as e:
            logger.bind(error=str(e)).error("tiktok_token_refresh_error")
            return None


async def _get_valid_access_token() -> str | None:
    """Get a valid access token, refreshing if needed."""
    config = get_config()

    # First try the configured access token
    if config.tiktok.access_token:
        return config.tiktok.access_token

    # Try refreshing
    return await refresh_access_token()


async def _init_video_post(
    client: httpx.AsyncClient,
    access_token: str,
    video_url: str,
    title: str,
) -> TikTokPostResult:
    """
    Initialize a video post using URL-based upload (pull from URL).

    Args:
        client: Async HTTP client
        access_token: Valid access token
        video_url: Public URL of the video (S3, R2, etc.)
        title: Video caption/title

    Returns:
        TikTokPostResult with publish_id if successful
    """
    config = get_config()

    # Truncate title to TikTok's limit (2200 chars for description)
    caption = title[:2200] if len(title) > 2200 else title

    payload = {
        "post_info": {
            "title": caption,
            "privacy_level": config.tiktok.privacy_level,
            "disable_duet": config.tiktok.disable_duet,
            "disable_comment": config.tiktok.disable_comment,
            "disable_stitch": config.tiktok.disable_stitch,
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "video_url": video_url,
        },
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }

    try:
        resp = await client.post(
            TIKTOK_POST_INIT_URL,
            json=payload,
            headers=headers,
        )

        data = resp.json()

        if resp.status_code == 200 and data.get("error", {}).get("code") == "ok":
            publish_id = data.get("data", {}).get("publish_id")
            return TikTokPostResult(
                publish_id=publish_id,
                success=True,
            )
        else:
            error_msg = data.get("error", {}).get("message", "Unknown error")
            error_code = data.get("error", {}).get("code", "unknown")
            return TikTokPostResult(
                publish_id=None,
                success=False,
                error=f"{error_code}: {error_msg}",
            )

    except httpx.TimeoutException:
        return TikTokPostResult(
            publish_id=None,
            success=False,
            error="Request timed out",
        )
    except Exception as e:
        return TikTokPostResult(
            publish_id=None,
            success=False,
            error=str(e),
        )


async def _check_post_status(
    client: httpx.AsyncClient,
    access_token: str,
    publish_id: str,
) -> dict[str, Any]:
    """
    Check the status of a video post.

    Args:
        client: Async HTTP client
        access_token: Valid access token
        publish_id: Publish ID from init response

    Returns:
        Status dict with 'status' key
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }

    try:
        resp = await client.post(
            TIKTOK_POST_STATUS_URL,
            json={"publish_id": publish_id},
            headers=headers,
        )

        if resp.status_code == 200:
            data: dict[str, Any] = resp.json().get("data", {})
            return data
        else:
            return {"status": "FAILED", "error": resp.text[:200]}

    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


async def _post_video_with_retry(
    client: httpx.AsyncClient,
    access_token: str,
    video_url: str,
    title: str,
    max_retries: int = 3,
) -> TikTokPostResult:
    """Post video with retry logic."""
    config = get_config()

    for attempt in range(max_retries):
        result = await _init_video_post(client, access_token, video_url, title)

        if result.success:
            return result

        # Check for rate limit or transient errors
        if result.error and ("rate" in result.error.lower() or "retry" in result.error.lower()):
            delay = config.tiktok.retry_delay_seconds * (attempt + 1)
            logger.bind(attempt=attempt, delay=delay).warning("tiktok_rate_limited")
            await asyncio.sleep(delay)
            continue

        # Non-recoverable error
        break

    return result


def build_video_caption(item: dict[str, Any], rank: int, issue_date: date | None = None) -> str:
    """
    Build a TikTok caption from an issue item.

    Args:
        item: Issue item with headline, teaser, etc.
        rank: Story rank (1-10)
        issue_date: Date of the issue

    Returns:
        Formatted caption for TikTok
    """
    config = get_config()

    headline = item.get("headline", "")
    teaser = item.get("teaser", "")

    # Format date
    if issue_date:
        date_str = issue_date.strftime("%b %d, %Y")
    else:
        date_str = date.today().strftime("%b %d, %Y")

    # Build caption with date, headline and teaser
    caption = f"{date_str} | {headline}\n\n{teaser}"

    # Add hashtags if enabled
    if config.tiktok.include_hashtags:
        hashtags = config.tiktok.default_hashtags
        hashtag_str = " ".join(f"#{tag}" for tag in hashtags)
        caption = f"{caption}\n\n{hashtag_str}"

    # Add CTA
    caption = f"{caption}\n\nMore signal, less noise: noyau.news"

    return caption


async def post_tiktok_video(
    video_url: str,
    item: dict[str, Any],
    rank: int,
    issue_date: date | None = None,
) -> TikTokPostResult:
    """
    Post a single video to TikTok.

    Args:
        video_url: Public URL of the video
        item: Issue item for caption
        rank: Story rank
        issue_date: Date of the issue

    Returns:
        TikTokPostResult
    """
    access_token = await _get_valid_access_token()

    if not access_token:
        return TikTokPostResult(
            publish_id=None,
            success=False,
            error="No valid access token",
        )

    caption = build_video_caption(item, rank, issue_date)

    async with httpx.AsyncClient(timeout=60.0) as client:
        return await _post_video_with_retry(client, access_token, video_url, caption)


async def send_tiktok_videos(
    issue_date: date,
    videos: list[dict[str, Any]],
    items: list[dict[str, Any]],
) -> TikTokUploadResult:
    """
    Post daily digest videos to TikTok.

    Args:
        issue_date: Date of the issue
        videos: List of video results with s3_url
        items: List of issue items for captions

    Returns:
        TikTokUploadResult with success status
    """
    config = get_config()

    # Check if TikTok is enabled
    if not config.tiktok.enabled:
        logger.debug("tiktok_disabled")
        return TikTokUploadResult(
            results=[],
            success=False,
            message="TikTok posting is disabled",
        )

    # Check for credentials
    if not config.tiktok.client_key:
        logger.warning("tiktok_credentials_not_set")
        return TikTokUploadResult(
            results=[],
            success=False,
            message="TikTok credentials not configured",
        )

    results: list[TikTokPostResult] = []

    # Post top video (as per user decision: top 1 only)
    videos_to_post = videos[: config.tiktok.videos_per_day]

    for i, video in enumerate(videos_to_post):
        video_url = video.get("s3_url")

        if not video_url:
            logger.bind(rank=i + 1).warning("tiktok_no_video_url")
            results.append(
                TikTokPostResult(
                    publish_id=None,
                    success=False,
                    error="No S3 URL for video",
                )
            )
            continue

        # Match video to corresponding item for caption
        item = items[i] if i < len(items) else {}

        result = await post_tiktok_video(video_url, item, rank=i + 1, issue_date=issue_date)
        results.append(result)

        if result.success:
            logger.bind(
                rank=i + 1,
                publish_id=result.publish_id,
            ).info("tiktok_video_posted")
        else:
            logger.bind(
                rank=i + 1,
                error=result.error,
            ).warning("tiktok_video_post_failed")

    # Count successes
    successful = sum(1 for r in results if r.success)
    total = len(results)

    if successful == total and total > 0:
        return TikTokUploadResult(
            results=results,
            success=True,
            message=f"Posted {total} video(s) to TikTok",
        )
    elif successful > 0:
        return TikTokUploadResult(
            results=results,
            success=True,
            message=f"Partial success: {successful}/{total} videos posted",
        )
    else:
        return TikTokUploadResult(
            results=results,
            success=False,
            message="Failed to post any videos to TikTok",
        )
