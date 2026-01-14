"""
TikTok service for posting daily digest videos via TikTok Content Posting API.

Uses OAuth 2.0 for authentication. Requires one-time manual auth flow to get
refresh token, then auto-refreshes as needed.

Includes browser-based fallback using tiktok-uploader (Selenium + cookies)
when API is unavailable or not approved.

API Docs: https://developers.tiktok.com/doc/content-posting-api-get-started
"""

import asyncio
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
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


# ---------------------------------------------------------------------------
# Browser-based upload (Selenium fallback)
# ---------------------------------------------------------------------------


async def _download_video_to_temp(video_url: str) -> str | None:
    """
    Download video from URL to a temporary file for browser upload.

    Args:
        video_url: Public URL of the video (S3, R2, etc.)

    Returns:
        Path to temporary file if successful, None otherwise
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.get(video_url)
            if resp.status_code == 200:
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                    f.write(resp.content)
                    return f.name
            else:
                logger.bind(status=resp.status_code).error("video_download_failed")
        except Exception as e:
            logger.bind(error=str(e)).error("video_download_error")
    return None


def _get_chrome_driver(headless: bool = True):
    """Create Chrome driver with system chromium."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    options = Options()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = "/usr/bin/chromium"

    return webdriver.Chrome(
        service=Service("/usr/bin/chromedriver"),
        options=options,
    )


def _patch_tiktok_uploader_browser(headless: bool = True):
    """Monkey-patch tiktok-uploader to use system chromium."""
    import tiktok_uploader.browsers as tb

    tb.get_browser = lambda *args, **kwargs: _get_chrome_driver(headless)


def _handle_content_verification_modal(driver, timeout: int = 5) -> bool:
    """
    Handle TikTok's content verification modal if it appears.

    Presses Escape to dismiss the modal and waits for verification to complete
    naturally, rather than forcing an early publish.

    Returns:
        True if modal was found and handled, False otherwise
    """
    import time

    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions
    from selenium.webdriver.support.ui import WebDriverWait

    try:
        # Wait for modal to appear (short timeout - it may not appear)
        wait = WebDriverWait(driver, timeout)

        # Look for the modal
        wait.until(expected_conditions.presence_of_element_located((By.CSS_SELECTOR, ".TUXModal")))

        logger.info("tiktok_content_verification_modal_detected")

        # Click the primary button to proceed with publishing
        button = driver.find_element(By.CSS_SELECTOR, "button.TUXButton")
        button.click()
        logger.info("tiktok_modal_button_clicked")

        # Wait for verification to complete (up to 3 minutes total, checking every 60s)
        for attempt in range(3):
            logger.bind(attempt=attempt + 1).info("tiktok_waiting_for_verification")
            time.sleep(60)

            # Check if modal reappeared
            try:
                modal = driver.find_element(By.CSS_SELECTOR, ".TUXModal")
                if modal.is_displayed():
                    # Modal still there, click button again
                    btn = driver.find_element(By.CSS_SELECTOR, "button.TUXButton")
                    btn.click()
                    logger.info("tiktok_modal_button_clicked_again")
                else:
                    # Modal gone, verification likely complete
                    break
            except Exception:
                # Modal not found, verification complete
                break

        return True

    except Exception:
        # Modal didn't appear - that's fine
        return False


def _upload_via_browser(
    video_path: str,
    caption: str,
    cookies_path: str,
    headless: bool = True,
) -> TikTokPostResult:
    """
    Upload video using browser automation (tiktok-uploader).

    This is a synchronous function due to Selenium limitations.
    Run in executor when calling from async context.

    Includes handling for TikTok's content verification modal.

    Args:
        video_path: Local path to video file
        caption: Video caption/description
        cookies_path: Path to cookies.txt file (Netscape format)
        headless: Run browser in headless mode

    Returns:
        TikTokPostResult with success status
    """
    import time

    driver = None
    try:
        # Patch tiktok-uploader to use system chromium and get driver reference
        _patch_tiktok_uploader_browser(headless)

        # Store original get_browser to capture driver
        import tiktok_uploader.browsers as tb
        from tiktok_uploader.upload import upload_video

        captured_driver = None
        original_get_browser = tb.get_browser

        def capturing_get_browser(*args, **kwargs):
            nonlocal captured_driver
            captured_driver = original_get_browser(*args, **kwargs)
            return captured_driver

        tb.get_browser = capturing_get_browser

        # Start upload in a way that we can handle the modal
        # tiktok-uploader returns list of failed videos (empty = all succeeded)
        failed = upload_video(
            video_path,
            description=caption,
            cookies=cookies_path,
            headless=headless,
        )

        # If upload failed, check if it's due to content verification modal
        if failed and captured_driver:
            driver = captured_driver
            logger.info("tiktok_upload_failed_checking_modal")

            # Try to handle the content verification modal
            if _handle_content_verification_modal(driver, timeout=3):
                # Modal was handled, wait a bit and check if upload succeeds
                time.sleep(2)
                # The upload should continue automatically after modal dismiss
                logger.info("tiktok_modal_handled_waiting_for_completion")
                time.sleep(5)  # Wait for upload to complete
                failed = []  # Assume success after modal handling

        if not failed:
            logger.info("tiktok_browser_upload_success")
            return TikTokPostResult(
                publish_id="browser_upload",
                success=True,
            )
        else:
            logger.bind(failed=failed).warning("tiktok_browser_upload_failed")
            return TikTokPostResult(
                publish_id=None,
                success=False,
                error="Browser upload failed",
            )

    except ImportError:
        return TikTokPostResult(
            publish_id=None,
            success=False,
            error="tiktok-uploader not installed. Run: pip install tiktok-uploader",
        )
    except Exception as e:
        logger.bind(error=str(e)).error("tiktok_browser_upload_error")
        return TikTokPostResult(
            publish_id=None,
            success=False,
            error=f"Browser upload error: {e}",
        )
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


async def _try_browser_upload(
    video_url: str,
    caption: str,
    cookies_path: str,
    headless: bool = True,
) -> TikTokPostResult:
    """
    Attempt browser-based upload for a single video.

    Downloads video to temp file, uploads via Selenium, then cleans up.

    Args:
        video_url: Public URL of the video
        caption: Video caption/description
        cookies_path: Path to cookies.txt file
        headless: Run browser in headless mode

    Returns:
        TikTokPostResult with success status
    """
    # Download video to temp file
    temp_path = await _download_video_to_temp(video_url)
    if not temp_path:
        return TikTokPostResult(
            publish_id=None,
            success=False,
            error="Failed to download video for browser upload",
        )

    try:
        # Run sync Selenium upload in executor
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            _upload_via_browser,
            temp_path,
            caption,
            cookies_path,
            headless,
        )
        return result
    finally:
        # Clean up temp file
        Path(temp_path).unlink(missing_ok=True)


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

    # Check for cookies (browser upload only - no API)
    if not config.tiktok.cookies_path:
        logger.warning("tiktok_cookies_not_configured")
        return TikTokUploadResult(
            results=[],
            success=False,
            message="TikTok cookies path not configured (TIKTOK_COOKIES_PATH)",
        )

    if not Path(config.tiktok.cookies_path).exists():
        logger.warning("tiktok_cookies_file_not_found")
        return TikTokUploadResult(
            results=[],
            success=False,
            message=f"TikTok cookies file not found: {config.tiktok.cookies_path}",
        )

    results: list[TikTokPostResult] = []

    # Post top videos
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
        caption = build_video_caption(item, i + 1, issue_date)

        # Upload via browser (Selenium + cookies)
        result = await _try_browser_upload(
            video_url=video_url,
            caption=caption,
            cookies_path=config.tiktok.cookies_path,
            headless=config.tiktok.browser_headless,
        )

        if result.success:
            logger.bind(rank=i + 1).info("tiktok_video_posted")
        else:
            logger.bind(rank=i + 1, error=result.error).warning("tiktok_upload_failed")

        results.append(result)

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
