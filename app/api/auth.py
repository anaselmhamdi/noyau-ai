from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.config import get_config
from app.core.logging import get_logger
from app.core.security import (
    generate_ref_code,
    generate_session_id,
    generate_token,
    get_magic_link_expiry,
    get_session_expiry,
    hash_token,
    is_expired,
    verify_unsubscribe_token,
)
from app.dependencies import DBSession
from app.models.user import MagicLink, Session, User
from app.schemas.auth import MagicLinkRequest, MagicLinkResponse
from app.services.discord_service import send_discord_error
from app.services.email_service import send_magic_link_email
from app.services.email_validation import ValidationStatus, get_email_validator
from app.services.posthog_client import track_session_started, track_signup_completed
from app.services.tiktok_service import build_auth_url, exchange_code_for_tokens

logger = get_logger(__name__)

router = APIRouter()


@router.post("/request-link", response_model=MagicLinkResponse)
async def request_magic_link(
    body: MagicLinkRequest,
    db: DBSession,
) -> MagicLinkResponse:
    """
    Request a magic link for passwordless authentication.

    Validates email before sending a one-time login link.
    """
    # Validate email before creating magic link
    validator = get_email_validator()
    validation_result = await validator.validate(body.email)

    if not validator.should_allow(validation_result):
        logger.bind(
            email=body.email,
            status=validation_result.status,
            reason=validation_result.reason,
        ).warning("email_validation_rejected")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a valid email address",
        )

    # Log risky emails for monitoring (but allow them)
    if validation_result.status == ValidationStatus.RISKY:
        logger.bind(
            email=body.email,
            is_disposable=validation_result.is_disposable,
            is_role_based=validation_result.is_role_based,
        ).info("email_validation_risky")

    # Generate token and hash
    token = generate_token()
    token_hash = hash_token(token)

    # Create magic link record
    magic_link = MagicLink(
        token_hash=token_hash,
        email=body.email,
        redirect_path=body.redirect,
        expires_at=get_magic_link_expiry(),
    )
    db.add(magic_link)
    await db.flush()

    # Send email (async, don't wait)
    try:
        await send_magic_link_email(
            email=body.email,
            token=token,
            redirect_path=body.redirect,
        )

        # Track signup completed (magic link sent successfully)
        track_signup_completed(
            email=body.email,
            issue_date=None,  # Could be extracted from redirect path if needed
            validation_status=validation_result.status.value,
        )
    except Exception as e:
        # Log error but don't expose to user (to not leak email existence)
        logger.bind(error=str(e), email=body.email).error("magic_link_email_failed")
        # Report to Discord
        await send_discord_error(
            title="Magic Link Email Failed",
            error=str(e),
            context={"email": body.email, "endpoint": "/auth/request-link"},
        )

    return MagicLinkResponse()


@router.get("/magic")
async def verify_magic_link(
    token: str,
    redirect: str,
    response: Response,
    db: DBSession,
) -> Response:
    """
    Verify a magic link token and create a session.

    Sets a session cookie and redirects to the specified path.
    """
    # Hash the token to look up
    token_hash = hash_token(token)

    # Find the magic link
    result = await db.execute(select(MagicLink).where(MagicLink.token_hash == token_hash))
    magic_link = result.scalar_one_or_none()

    if not magic_link:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired link",
        )

    # Check if already used
    if magic_link.used_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This link has already been used",
        )

    # Check expiry
    if is_expired(magic_link.expires_at):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This link has expired",
        )

    # Mark as used
    from app.core.datetime_utils import utc_now

    magic_link.used_at = utc_now()

    # Find or create user
    user_result = await db.execute(select(User).where(User.email == magic_link.email))
    user = user_result.scalar_one_or_none()

    is_new_user = user is None
    if not user:
        # Create new user
        user = User(
            email=magic_link.email,
            ref_code=generate_ref_code(),
        )
        db.add(user)
        await db.flush()

    # Create session
    session = Session(
        id=generate_session_id(),
        user_id=user.id,
        expires_at=get_session_expiry(),
    )
    db.add(session)
    await db.flush()

    # Track session started event
    track_session_started(
        user_id=str(user.id),
        email=user.email,
        is_new_user=is_new_user,
        ref_code=user.ref_code,
    )

    # Get config for base URL
    config = get_config()

    # Set session cookie
    response.set_cookie(
        key="session_id",
        value=str(session.id),
        httponly=True,
        secure=config.settings.base_url.startswith("https"),
        samesite="lax",
        max_age=30 * 24 * 60 * 60,  # 30 days
    )

    # Redirect to the requested path
    response.status_code = status.HTTP_302_FOUND
    response.headers["Location"] = redirect or "/"

    return response


@router.get("/unsubscribe")
async def unsubscribe(
    db: DBSession,
    email: str = Query(...),
    token: str = Query(...),
) -> RedirectResponse:
    """
    Unsubscribe a user from email digests.

    Validates HMAC token and sets is_subscribed=False.
    """
    if not verify_unsubscribe_token(email, token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid unsubscribe link",
        )

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user:
        user.is_subscribed = False
        await db.commit()
        logger.bind(email=email).info("user_unsubscribed")

    # Redirect to confirmation page with token for resubscribe option
    return RedirectResponse(
        url=f"/unsubscribed?email={quote(email)}&token={token}",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/resubscribe")
async def resubscribe(
    db: DBSession,
    email: str = Query(...),
    token: str = Query(...),
) -> RedirectResponse:
    """
    Resubscribe a user to email digests.

    Validates HMAC token and sets is_subscribed=True.
    """
    if not verify_unsubscribe_token(email, token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid link",
        )

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user:
        user.is_subscribed = True
        await db.commit()
        logger.bind(email=email).info("user_resubscribed")

    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)


# -----------------------------------------------------------------------------
# TikTok OAuth (for initial token setup)
# -----------------------------------------------------------------------------


@router.get("/tiktok/tiktok5jv3QAzhtw6g0bwbctXEnI0OoLYipkiu.txt")
async def tiktok_verification_auth_path() -> str:
    """TikTok domain verification file for /auth/tiktok/ prefix."""
    return "tiktok-developers-site-verification=5jv3QAzhtw6g0bwbctXEnI0OoLYipkiu"


@router.get("/tiktok/authorize")
async def tiktok_authorize() -> RedirectResponse:
    """
    Redirect to TikTok OAuth authorization page.

    This is a one-time setup flow to get the initial access/refresh tokens.
    Visit this endpoint in a browser to start the OAuth flow.
    """
    import secrets

    state = secrets.token_urlsafe(16)
    auth_url = build_auth_url(state=state)

    logger.info("tiktok_oauth_started")
    return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)


@router.get("/tiktok/callback")
async def tiktok_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    error_description: str = Query(None),
) -> dict:
    """
    Handle TikTok OAuth callback.

    Exchanges the authorization code for access/refresh tokens.
    Returns the tokens so you can save them to your .env file.
    """
    if error:
        logger.bind(error=error, description=error_description).error("tiktok_oauth_error")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"TikTok OAuth error: {error_description or error}",
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No authorization code received",
        )

    # Exchange code for tokens
    tokens = await exchange_code_for_tokens(code)

    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to exchange code for tokens",
        )

    logger.bind(open_id=tokens.open_id).info("tiktok_oauth_completed")

    # Return tokens for manual configuration
    # In production, you'd store these securely
    return {
        "message": "TikTok OAuth successful! Save these to your .env file:",
        "tokens": {
            "TIKTOK_ACCESS_TOKEN": tokens.access_token,
            "TIKTOK_REFRESH_TOKEN": tokens.refresh_token,
            "TIKTOK_OPEN_ID": tokens.open_id,
        },
        "expires_in_seconds": tokens.expires_in,
        "note": "Access token expires, but refresh token is long-lived. Store TIKTOK_REFRESH_TOKEN in .env",
    }
