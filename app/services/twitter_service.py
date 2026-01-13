"""
Twitter service for posting daily digest threads via Twitter API v2.

Uses OAuth 1.0a for user authentication to post tweets.
Follows the same patterns as discord_service.py for consistency.
"""

import asyncio
import base64
import hashlib
import hmac
import time
import urllib.parse
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from app.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

TWITTER_API_URL = "https://api.twitter.com/2/tweets"


@dataclass
class TweetResult:
    """Result of posting a single tweet."""

    tweet_id: str | None
    text: str
    success: bool
    error: str | None = None


@dataclass
class ThreadResult:
    """Result of posting a thread."""

    intro_tweet_id: str | None
    tweet_results: list[TweetResult]
    success: bool
    message: str


def _generate_oauth_signature(
    method: str,
    url: str,
    params: dict[str, str],
    consumer_secret: str,
    token_secret: str,
) -> str:
    """Generate OAuth 1.0a signature for Twitter API requests."""
    # Sort and encode parameters
    sorted_params = sorted(params.items())
    param_string = "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
        for k, v in sorted_params
    )

    # Create signature base string
    base_string = "&".join(
        [
            method.upper(),
            urllib.parse.quote(url, safe=""),
            urllib.parse.quote(param_string, safe=""),
        ]
    )

    # Create signing key
    signing_key = f"{urllib.parse.quote(consumer_secret, safe='')}&{urllib.parse.quote(token_secret, safe='')}"

    # Generate HMAC-SHA1 signature
    signature = hmac.new(
        signing_key.encode("utf-8"),
        base_string.encode("utf-8"),
        hashlib.sha1,
    ).digest()

    return base64.b64encode(signature).decode("utf-8")


def _generate_oauth_header(
    method: str,
    url: str,
    api_key: str,
    api_secret: str,
    access_token: str,
    access_token_secret: str,
) -> str:
    """Generate OAuth 1.0a Authorization header for Twitter API."""
    oauth_params = {
        "oauth_consumer_key": api_key,
        "oauth_nonce": base64.b64encode(hashlib.sha256(str(time.time()).encode()).digest()).decode(
            "utf-8"
        )[:32],
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": access_token,
        "oauth_version": "1.0",
    }

    # Generate signature
    signature = _generate_oauth_signature(
        method=method,
        url=url,
        params=oauth_params,
        consumer_secret=api_secret,
        token_secret=access_token_secret,
    )
    oauth_params["oauth_signature"] = signature

    # Build Authorization header
    auth_header = "OAuth " + ", ".join(
        f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(v, safe="")}"'
        for k, v in sorted(oauth_params.items())
    )

    return auth_header


async def _post_tweet(
    client: httpx.AsyncClient,
    text: str,
    reply_to_id: str | None = None,
) -> TweetResult:
    """
    Post a single tweet using Twitter API v2.

    Args:
        client: Async HTTP client
        text: Tweet content (max 280 chars)
        reply_to_id: Optional tweet ID to reply to (for threads)

    Returns:
        TweetResult with tweet_id and status
    """
    config = get_config()

    payload: dict[str, Any] = {"text": text}
    if reply_to_id:
        payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}

    auth_header = _generate_oauth_header(
        method="POST",
        url=TWITTER_API_URL,
        api_key=config.twitter.api_key,
        api_secret=config.twitter.api_secret,
        access_token=config.twitter.access_token,
        access_token_secret=config.twitter.access_token_secret,
    )

    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json",
    }

    try:
        resp = await client.post(TWITTER_API_URL, json=payload, headers=headers)

        if resp.status_code == 201:
            data = resp.json()
            tweet_id = data.get("data", {}).get("id")
            logger.bind(tweet_id=tweet_id).debug("tweet_posted")
            return TweetResult(
                tweet_id=tweet_id,
                text=text,
                success=True,
            )
        elif resp.status_code == 429:
            logger.warning("twitter_rate_limit_exceeded")
            return TweetResult(
                tweet_id=None,
                text=text,
                success=False,
                error="Rate limit exceeded",
            )
        elif resp.status_code == 401:
            logger.bind(response=resp.text[:500] if resp.text else "").error("twitter_auth_failed")
            return TweetResult(
                tweet_id=None,
                text=text,
                success=False,
                error="Authentication failed - check API credentials",
            )
        else:
            error_detail = resp.text[:500] if resp.text else "Unknown error"
            logger.bind(
                status_code=resp.status_code,
                response=error_detail,
            ).error("twitter_api_error")
            return TweetResult(
                tweet_id=None,
                text=text,
                success=False,
                error=f"HTTP {resp.status_code}: {error_detail}",
            )
    except httpx.TimeoutException:
        return TweetResult(
            tweet_id=None,
            text=text,
            success=False,
            error="Request timed out",
        )
    except Exception as e:
        return TweetResult(
            tweet_id=None,
            text=text,
            success=False,
            error=str(e),
        )


async def _post_tweet_with_retry(
    client: httpx.AsyncClient,
    text: str,
    reply_to_id: str | None = None,
) -> TweetResult:
    """Post tweet with automatic retry on rate limit."""
    config = get_config()

    for attempt in range(config.twitter.max_retries):
        result = await _post_tweet(client, text, reply_to_id)

        if result.success:
            return result

        if result.error and "rate limit" in result.error.lower():
            delay = config.twitter.retry_delay_seconds * (attempt + 1)
            logger.bind(attempt=attempt, delay=delay).warning("twitter_rate_limited")
            await asyncio.sleep(delay)
            continue

        # Non-recoverable error
        break

    return result


def build_intro_tweet(issue_date: date) -> str:
    """
    Build the intro tweet for the thread.

    Args:
        issue_date: Date of the issue

    Returns:
        Formatted intro tweet text
    """
    config = get_config()
    template = config.twitter.intro_template

    formatted_date = issue_date.strftime("%B %d, %Y")
    return template.format(date=formatted_date)


def build_outro_tweet() -> str:
    """
    Build the outro tweet for the thread.

    Returns:
        Formatted outro tweet text with CTA
    """
    config = get_config()
    return config.twitter.outro_template


def _extract_primary_source_url(citations: list[dict[str, Any]] | None) -> str:
    """
    Extract the primary source URL from citations.

    Args:
        citations: List of citation dicts with url and label

    Returns:
        URL string or empty string if none found
    """
    if not citations:
        return ""

    for citation in citations:
        if isinstance(citation, dict):
            url = citation.get("url", "")
            if url:
                return str(url)

    return ""


def build_story_tweet(rank: int, item: dict[str, Any]) -> str:
    """
    Build a story tweet from an issue item.

    Respects Twitter's 280 character limit by prioritizing
    headline over teaser when truncation is needed.

    Args:
        rank: Story rank (1-10)
        item: Issue item with headline, teaser, citations

    Returns:
        Formatted tweet text (max 280 chars)
    """
    headline = item.get("headline", "")
    teaser = item.get("teaser", "")
    citations = item.get("citations", [])
    url = _extract_primary_source_url(citations)

    # Format: "{rank}/10: {headline}\n\n{teaser}\n\n{url}"
    prefix = f"{rank}/10: "
    url_section = f"\n\n{url}" if url else ""

    # Twitter shortens URLs to ~23 chars with t.co, reserve 25 for safety
    url_chars = 25 if url else 0

    # Calculate available chars for content
    # 280 - prefix - url_chars - 4 (for \n\n between headline and teaser)
    available = 280 - len(prefix) - url_chars - 4

    # Prioritize headline, truncate teaser if needed
    if len(headline) + len(teaser) <= available:
        content = f"{headline}\n\n{teaser}"
    elif len(headline) <= available:
        # Truncate teaser with ellipsis
        teaser_budget = available - len(headline) - 3  # -3 for "..."
        if teaser_budget > 20:  # Only include if meaningful
            content = f"{headline}\n\n{teaser[:teaser_budget]}..."
        else:
            content = headline
    else:
        # Truncate headline (rare case)
        content = headline[: available - 3] + "..."

    return f"{prefix}{content}{url_section}"


async def post_twitter_thread(
    issue_date: date,
    items: list[dict[str, Any]],
) -> ThreadResult:
    """
    Post a daily digest thread to Twitter.

    Creates an intro tweet followed by story tweets as replies,
    forming a thread. Handles rate limits and errors gracefully.

    Args:
        issue_date: Date of the issue
        items: List of issue items with summaries

    Returns:
        ThreadResult with success status and tweet IDs
    """
    tweet_results: list[TweetResult] = []
    intro_tweet_id: str | None = None

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Post intro tweet
        intro_text = build_intro_tweet(issue_date)
        intro_result = await _post_tweet_with_retry(client, intro_text)
        tweet_results.append(intro_result)

        if not intro_result.success:
            return ThreadResult(
                intro_tweet_id=None,
                tweet_results=tweet_results,
                success=False,
                message=f"Failed to post intro tweet: {intro_result.error}",
            )

        intro_tweet_id = intro_result.tweet_id
        previous_tweet_id = intro_tweet_id

        # Post story tweets as replies
        for rank, item in enumerate(items[:10], start=1):
            story_text = build_story_tweet(rank, item)
            story_result = await _post_tweet_with_retry(
                client, story_text, reply_to_id=previous_tweet_id
            )
            tweet_results.append(story_result)

            if story_result.success:
                previous_tweet_id = story_result.tweet_id
            else:
                logger.bind(
                    rank=rank,
                    error=story_result.error,
                ).warning("twitter_story_tweet_failed")
                # Continue with next story, using previous successful tweet as parent

        # Post outro tweet with CTA
        outro_text = build_outro_tweet()
        outro_result = await _post_tweet_with_retry(
            client, outro_text, reply_to_id=previous_tweet_id
        )
        tweet_results.append(outro_result)

        if not outro_result.success:
            logger.bind(error=outro_result.error).warning("twitter_outro_tweet_failed")

    # Count successes
    successful = sum(1 for r in tweet_results if r.success)
    total = len(tweet_results)

    if successful == total:
        return ThreadResult(
            intro_tweet_id=intro_tweet_id,
            tweet_results=tweet_results,
            success=True,
            message=f"Posted thread with {total} tweets",
        )
    elif successful > 1:
        return ThreadResult(
            intro_tweet_id=intro_tweet_id,
            tweet_results=tweet_results,
            success=True,  # Partial success
            message=f"Partial thread: {successful}/{total} tweets posted",
        )
    else:
        return ThreadResult(
            intro_tweet_id=intro_tweet_id,
            tweet_results=tweet_results,
            success=False,
            message="Thread posting failed",
        )


async def send_twitter_digest(issue_date: date, items: list[dict[str, Any]]) -> bool:
    """
    Send daily digest to Twitter via thread.

    Main entry point matching discord_service pattern.

    Args:
        issue_date: Date of the issue
        items: List of issue items with summaries

    Returns:
        True if successful, False otherwise
    """
    config = get_config()

    # Check if Twitter is enabled
    if not config.twitter.enabled:
        logger.debug("twitter_disabled")
        return False

    # Check for credentials
    if not config.twitter.api_key or not config.twitter.access_token:
        logger.warning("twitter_credentials_not_set")
        return False

    try:
        result = await post_twitter_thread(issue_date, items)

        if result.success:
            logger.bind(
                date=str(issue_date),
                items=len(items),
                intro_id=result.intro_tweet_id,
                message=result.message,
            ).info("twitter_thread_posted")
            return True
        else:
            # Log detailed failure info including individual tweet errors
            failed_tweets = [t for t in result.tweet_results if not t.success]
            errors = [t.error for t in failed_tweets if t.error]
            logger.bind(
                message=result.message,
                failed_count=len(failed_tweets),
                errors=errors[:5],  # First 5 errors
            ).warning("twitter_thread_failed")
            return False

    except Exception as e:
        logger.bind(error=str(e)).error("twitter_send_error")
        return False
