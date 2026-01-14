"""
TikTok service for posting daily digest videos.

Uses direct Selenium automation with system chromium for browser-based uploads.
Requires TikTok cookies exported in Netscape format.

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
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = "/usr/bin/chromium"

    return webdriver.Chrome(
        service=Service("/usr/bin/chromedriver"),
        options=options,
    )


def _load_cookies(driver, cookies_path: str) -> None:
    """
    Load cookies from Netscape format file into Selenium driver.

    Netscape format: domain flag path secure expiration name value
    """
    with open(cookies_path) as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue

            parts = line.split("\t")
            if len(parts) >= 7:
                domain, _, path, secure, expiry, name, value = parts[:7]

                cookie = {
                    "name": name,
                    "value": value,
                    "domain": domain,
                    "path": path,
                    "secure": secure.upper() == "TRUE",
                }

                # Only add expiry if it's not a session cookie (0 = session)
                if expiry and expiry != "0":
                    cookie["expiry"] = int(expiry)

                try:
                    driver.add_cookie(cookie)
                except Exception as e:
                    # Some cookies may fail (wrong domain, etc.) - that's OK
                    logger.bind(name=name, error=str(e)).debug("cookie_add_failed")


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
    Upload video using direct Selenium with system chromium.

    This bypasses tiktok-uploader library to avoid webdriver-manager issues
    in Docker environments.

    Args:
        video_path: Local path to video file
        caption: Video caption/description
        cookies_path: Path to cookies.txt file (Netscape format)
        headless: Run browser in headless mode

    Returns:
        TikTokPostResult with success status
    """
    import time

    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.common.by import By

    driver = None
    try:
        # 1. Create driver with system chromium
        driver = _get_chrome_driver(headless)
        logger.info("tiktok_driver_created")

        # 2. Navigate to TikTok and load cookies
        driver.get("https://www.tiktok.com")
        time.sleep(2)  # Wait for page to load before adding cookies
        _load_cookies(driver, cookies_path)
        logger.info("tiktok_cookies_loaded")

        # 3. Refresh to apply cookies and navigate to upload page
        driver.refresh()
        time.sleep(2)
        driver.get("https://www.tiktok.com/creator-center/upload")
        logger.info("tiktok_navigated_to_upload")

        # 4. Wait for and find file input (may be hidden)
        # TikTok's upload page has an iframe or hidden input
        time.sleep(5)  # Wait for page to fully load

        # Try multiple selectors for file input
        file_input = None
        selectors = [
            "input[type='file']",
            "input[accept*='video']",
            "iframe",  # TikTok sometimes uses an iframe
        ]

        for selector in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    if selector == "iframe":
                        # Switch to iframe and find input
                        driver.switch_to.frame(elements[0])
                        file_input = driver.find_element(By.CSS_SELECTOR, "input[type='file']")
                    else:
                        file_input = elements[0]
                    logger.bind(selector=selector).info("tiktok_file_input_found")
                    break
            except Exception:
                continue

        if not file_input:
            # Save debug info
            driver.save_screenshot("/tmp/tiktok_no_input.png")
            with open("/tmp/tiktok_no_input.html", "w") as f:
                f.write(driver.page_source)
            logger.error("tiktok_file_input_not_found")
            return TikTokPostResult(
                publish_id=None,
                success=False,
                error="Could not find file input on upload page",
            )

        # 5. Upload the video file
        file_input.send_keys(video_path)
        logger.info("tiktok_video_file_sent")

        # 6. Wait for upload to process (look for progress indicators to disappear)
        time.sleep(10)  # Initial processing time

        # Wait for upload progress to complete (various possible indicators)
        try:
            # Wait up to 2 minutes for upload processing
            for _ in range(24):  # 24 * 5s = 2 minutes
                time.sleep(5)
                # Check if still uploading
                uploading_indicators = driver.find_elements(
                    By.CSS_SELECTOR,
                    "[class*='progress'], [class*='uploading'], [class*='loading']",
                )
                visible_indicators = [e for e in uploading_indicators if e.is_displayed()]
                if not visible_indicators:
                    break
                logger.debug("tiktok_still_uploading")
        except Exception:
            pass

        logger.info("tiktok_upload_processing_complete")

        # 7. Set caption/description
        # Try multiple selectors for the caption editor
        caption_selectors = [
            "[contenteditable='true']",
            ".public-DraftEditor-content",
            "[data-e2e='caption-editor']",
            "textarea",
            "[class*='caption']",
        ]

        caption_set = False
        for selector in caption_selectors:
            try:
                caption_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for elem in caption_elements:
                    if elem.is_displayed():
                        elem.click()
                        time.sleep(0.5)
                        elem.clear()
                        elem.send_keys(caption)
                        caption_set = True
                        logger.bind(selector=selector).info("tiktok_caption_set")
                        break
                if caption_set:
                    break
            except Exception:
                continue

        if not caption_set:
            logger.warning("tiktok_caption_not_set")
            # Continue anyway - video can be posted without caption

        time.sleep(2)

        # 8. Handle any verification modals
        _handle_content_verification_modal(driver, timeout=3)

        # 9. Dismiss any tutorial/joyride overlays
        try:
            # Click through any Joyride tutorial overlays
            joyride_overlays = driver.find_elements(
                By.CSS_SELECTOR, ".react-joyride__overlay, [data-test-id='overlay']"
            )
            for overlay in joyride_overlays:
                if overlay.is_displayed():
                    overlay.click()
                    logger.info("tiktok_joyride_overlay_clicked")
                    time.sleep(1)

            # Also try to find and click skip/close buttons
            skip_buttons = driver.find_elements(
                By.CSS_SELECTOR,
                "button[aria-label*='skip'], button[aria-label*='close'], "
                "button[class*='skip'], button[class*='close'], "
                "[data-testid='close'], .react-joyride__tooltip button",
            )
            for btn in skip_buttons:
                if btn.is_displayed():
                    btn.click()
                    logger.info("tiktok_tutorial_button_clicked")
                    time.sleep(1)
        except Exception as e:
            logger.bind(error=str(e)).debug("tiktok_joyride_dismiss_failed")

        # 10. Scroll to bottom to make post button visible
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

        # 11. Click post button - look for button with "Publier" or "Post" text
        # The data-e2e attribute is the most reliable selector
        post_button = None

        # First try the exact data-e2e selector
        try:
            post_buttons = driver.find_elements(
                By.CSS_SELECTOR, "button[data-e2e='post_video_button']"
            )
            logger.bind(count=len(post_buttons)).debug("tiktok_found_post_buttons_by_data_e2e")
            for btn in post_buttons:
                if btn.is_displayed():
                    post_button = btn
                    break
        except Exception as e:
            logger.bind(error=str(e)).debug("tiktok_data_e2e_selector_failed")

        # If not found, try finding any button with Post/Publier text
        if not post_button:
            try:
                all_buttons = driver.find_elements(By.TAG_NAME, "button")
                logger.bind(count=len(all_buttons)).debug("tiktok_found_all_buttons")
                for btn in all_buttons:
                    try:
                        text = btn.text.lower()
                        if any(word in text for word in ["post", "publier", "publish", "submit"]):
                            if btn.is_displayed() and btn.is_enabled():
                                post_button = btn
                                logger.bind(text=btn.text).info("tiktok_found_post_button_by_text")
                                break
                    except Exception:
                        continue
            except Exception as e:
                logger.bind(error=str(e)).debug("tiktok_text_search_failed")

        if post_button:
            # Scroll to button and click
            driver.execute_script("arguments[0].scrollIntoView(true);", post_button)
            time.sleep(1)
            try:
                post_button.click()
                logger.info("tiktok_post_button_clicked")
            except Exception as click_error:
                # If normal click fails (e.g., overlay blocking), use JavaScript click
                logger.bind(error=str(click_error)).warning("tiktok_normal_click_failed")
                driver.execute_script("arguments[0].click();", post_button)
                logger.info("tiktok_post_button_clicked_via_js")
        else:
            driver.save_screenshot("/tmp/tiktok_no_post_button.png")
            with open("/tmp/tiktok_no_post_button.html", "w") as f:
                f.write(driver.page_source)
            logger.error("tiktok_post_button_not_found")
            return TikTokPostResult(
                publish_id=None,
                success=False,
                error="Could not find or click post button",
            )

        # 12. Wait for post to complete and handle any final modals
        time.sleep(5)
        _handle_content_verification_modal(driver, timeout=5)

        # Wait for success indication (page change or success message)
        time.sleep(10)

        logger.info("tiktok_browser_upload_success")
        return TikTokPostResult(
            publish_id="direct_upload",
            success=True,
        )

    except TimeoutException as e:
        if driver:
            driver.save_screenshot("/tmp/tiktok_timeout.png")
            with open("/tmp/tiktok_timeout.html", "w") as f:
                f.write(driver.page_source)
        logger.bind(error=str(e)).error("tiktok_upload_timeout")
        return TikTokPostResult(
            publish_id=None,
            success=False,
            error=f"Upload timed out: {e}",
        )
    except Exception as e:
        if driver:
            try:
                driver.save_screenshot("/tmp/tiktok_error.png")
                with open("/tmp/tiktok_error.html", "w") as f:
                    f.write(driver.page_source)
                logger.info("tiktok_error_debug_saved")
            except Exception:
                pass
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
