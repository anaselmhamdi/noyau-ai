"""
PostHog analytics client for server-side event tracking.

This module provides a singleton PostHog client that can be used throughout
the application to track events, identify users, and set user properties.
"""

import os
from functools import lru_cache
from typing import Any

from posthog import Posthog

from app.core.logging import get_logger

logger = get_logger(__name__)


# Event name constants for type safety
class Events:
    # Acquisition
    PAGE_VIEWED = "page_viewed"
    LANDING_PAGE_VIEWED = "landing_page_viewed"
    ISSUE_PAGE_VIEWED = "issue_page_viewed"

    # Activation
    SIGNUP_STARTED = "signup_started"
    SIGNUP_COMPLETED = "signup_completed"
    MAGIC_LINK_CLICKED = "magic_link_clicked"
    SESSION_STARTED = "session_started"

    # Retention
    EMAIL_DELIVERED = "email_delivered"
    EMAIL_OPENED = "email_opened"
    EMAIL_CLICKED = "email_clicked"
    RETURN_VISIT = "return_visit"

    # Referral
    SHARE_SNIPPET_COPIED = "share_snippet_copied"
    REFERRAL_LANDING = "referral_landing"
    REFERRAL_SIGNUP = "referral_signup"


@lru_cache(maxsize=1)
def get_posthog_client() -> Posthog | None:
    """
    Get or create the singleton PostHog client.

    Returns None if POSTHOG_API_KEY is not configured.
    """
    api_key = os.getenv("POSTHOG_API_KEY")
    host = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com")

    if not api_key:
        logger.bind(hint="Set POSTHOG_API_KEY to enable analytics").warning(
            "posthog_not_configured"
        )
        return None

    client = Posthog(
        api_key=api_key,
        host=host,
        debug=os.getenv("DEBUG", "false").lower() == "true",
    )

    logger.bind(host=host).info("posthog_initialized")
    return client


def capture(
    distinct_id: str,
    event: str,
    properties: dict[str, Any] | None = None,
) -> None:
    """
    Capture an event for a user.

    Args:
        distinct_id: User ID or anonymous ID
        event: Event name (use Events constants)
        properties: Additional event properties
    """
    client = get_posthog_client()
    if client is None:
        return

    try:
        client.capture(
            distinct_id=distinct_id,
            event=event,
            properties=properties or {},
        )
    except Exception as e:
        logger.bind(event=event, error=str(e)).error("posthog_capture_failed")


def identify(
    distinct_id: str,
    properties: dict[str, Any] | None = None,
) -> None:
    """
    Identify a user and set their properties.

    Args:
        distinct_id: User ID
        properties: User properties to set (email, signup_date, etc.)
    """
    client = get_posthog_client()
    if client is None:
        return

    try:
        client.identify(
            distinct_id=distinct_id,
            properties=properties or {},
        )
    except Exception as e:
        logger.bind(distinct_id=distinct_id, error=str(e)).error("posthog_identify_failed")


def alias(alias_id: str, distinct_id: str) -> None:
    """
    Create an alias between two user IDs.

    Useful for linking anonymous IDs to authenticated user IDs.

    Args:
        alias_id: The new ID (usually the authenticated user ID)
        distinct_id: The old ID (usually the anonymous ID)
    """
    client = get_posthog_client()
    if client is None:
        return

    try:
        client.alias(alias_id=alias_id, distinct_id=distinct_id)
    except Exception as e:
        logger.bind(alias_id=alias_id, error=str(e)).error("posthog_alias_failed")


def set_user_properties(distinct_id: str, properties: dict[str, Any]) -> None:
    """
    Set properties on a user without triggering an event.

    Args:
        distinct_id: User ID
        properties: Properties to set
    """
    client = get_posthog_client()
    if client is None:
        return

    try:
        # PostHog Python SDK uses identify for setting properties
        client.identify(
            distinct_id=distinct_id,
            properties=properties,
        )
    except Exception as e:
        logger.bind(distinct_id=distinct_id, error=str(e)).error("posthog_set_properties_failed")


def track_signup_completed(
    email: str,
    issue_date: str | None = None,
    validation_status: str = "unknown",
) -> None:
    """Track when a magic link is successfully sent."""
    email_domain = email.split("@")[1] if "@" in email else "unknown"
    capture(
        distinct_id=email,  # Use email as distinct_id before user is created
        event=Events.SIGNUP_COMPLETED,
        properties={
            "email_domain": email_domain,
            "issue_date": issue_date,
            "validation_status": validation_status,
        },
    )


def track_session_started(
    user_id: str,
    email: str,
    is_new_user: bool,
    ref_code: str | None = None,
    signup_source: str | None = None,
) -> None:
    """Track when a user successfully authenticates and starts a session."""
    # Identify the user with their properties
    identify(
        distinct_id=str(user_id),
        properties={
            "$email": email,
            "email_domain": email.split("@")[1] if "@" in email else "unknown",
        },
    )

    # Capture the session started event
    capture(
        distinct_id=str(user_id),
        event=Events.SESSION_STARTED,
        properties={
            "is_new_user": is_new_user,
            "ref_code": ref_code,
            "signup_source": signup_source,
        },
    )

    # If this is a new user, set additional properties
    if is_new_user:
        from app.core.datetime_utils import utc_now

        set_user_properties(
            str(user_id),
            {
                "signup_date": utc_now().isoformat(),
                "ref_code": ref_code,  # Their personal referral code
            },
        )


def track_email_delivered(
    user_id: str,
    email: str,
    issue_date: str,
) -> None:
    """Track when a digest email is successfully delivered."""
    capture(
        distinct_id=str(user_id),
        event=Events.EMAIL_DELIVERED,
        properties={
            "issue_date": issue_date,
            "email_domain": email.split("@")[1] if "@" in email else "unknown",
        },
    )


def track_referral_signup(
    user_id: str,
    referrer_user_id: str,
    ref_code: str,
) -> None:
    """Track when a referred user signs up."""
    capture(
        distinct_id=str(user_id),
        event=Events.REFERRAL_SIGNUP,
        properties={
            "ref_code": ref_code,
            "referrer_user_id": str(referrer_user_id),
        },
    )

    # Increment the referrer's referral count
    set_user_properties(
        str(referrer_user_id),
        {"$inc": {"referral_count": 1}},
    )


def shutdown() -> None:
    """Flush any pending events and shutdown the client."""
    client = get_posthog_client()
    if client is not None:
        client.shutdown()
