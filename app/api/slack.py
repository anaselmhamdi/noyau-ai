"""Slack OAuth endpoints for app installation."""

import secrets
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.config import get_config, get_settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.core.security import generate_ref_code
from app.models.messaging import MessagingConnection
from app.models.user import User
from app.services.slack_service import exchange_code_for_tokens, get_user_email

logger = get_logger(__name__)
router = APIRouter()


@router.get("/connect")
async def slack_connect() -> RedirectResponse:
    """
    Initiate Slack OAuth flow.

    Redirects to Slack authorization page.
    """
    config = get_config()
    settings = get_settings()

    if not config.slack.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack integration is not enabled",
        )

    if not config.slack.client_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Slack client ID not configured",
        )

    # Generate state for CSRF protection
    state = secrets.token_urlsafe(16)

    redirect_uri = f"{settings.base_url}/auth/slack/callback"

    # Build OAuth URL
    from app.services.slack_service import build_oauth_url

    auth_url = build_oauth_url(redirect_uri=redirect_uri, state=state)

    logger.info("slack_oauth_started")
    return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)


@router.get("/callback")
async def slack_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
) -> RedirectResponse:
    """
    Handle Slack OAuth callback.

    - Exchanges code for access token
    - Creates user account if needed (using Slack email)
    - Stores connection in messaging_connections
    """
    settings = get_settings()

    if error:
        logger.bind(error=error).warning("slack_oauth_cancelled")
        return RedirectResponse(
            url=f"{settings.base_url}/?slack=error&message={quote(error)}",
            status_code=status.HTTP_302_FOUND,
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No authorization code received",
        )

    # Exchange code for tokens
    redirect_uri = f"{settings.base_url}/auth/slack/callback"
    oauth_result = await exchange_code_for_tokens(code, redirect_uri)

    if not oauth_result:
        return RedirectResponse(
            url=f"{settings.base_url}/?slack=error&message=token_exchange_failed",
            status_code=status.HTTP_302_FOUND,
        )

    async with AsyncSessionLocal() as db:
        try:
            # Get user email
            email = oauth_result.authed_user_email

            # If no email in OAuth response, try to fetch it
            if not email and oauth_result.authed_user_id:
                email = await get_user_email(oauth_result.access_token, oauth_result.authed_user_id)

            if not email:
                return RedirectResponse(
                    url=f"{settings.base_url}/?slack=error&message=no_email",
                    status_code=status.HTTP_302_FOUND,
                )

            email = email.lower().strip()

            # Find or create user
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()

            if not user:
                user = User(
                    email=email,
                    ref_code=generate_ref_code(),
                )
                db.add(user)
                await db.flush()
                logger.bind(email=email, source="slack").info("user_created")

            # Check for existing connection
            result = await db.execute(
                select(MessagingConnection).where(
                    MessagingConnection.platform == "slack",
                    MessagingConnection.platform_user_id == oauth_result.authed_user_id,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Update existing connection
                existing.access_token = oauth_result.access_token
                existing.platform_team_id = oauth_result.team_id
                existing.platform_team_name = oauth_result.team_name
                existing.is_active = True
                existing.user_id = user.id
                logger.bind(
                    slack_user_id=oauth_result.authed_user_id,
                    team_id=oauth_result.team_id,
                ).info("slack_connection_updated")
            else:
                # Create new connection
                connection = MessagingConnection(
                    user_id=user.id,
                    platform="slack",
                    platform_user_id=oauth_result.authed_user_id,
                    platform_team_id=oauth_result.team_id,
                    platform_team_name=oauth_result.team_name,
                    access_token=oauth_result.access_token,
                )
                db.add(connection)
                logger.bind(
                    slack_user_id=oauth_result.authed_user_id,
                    team_id=oauth_result.team_id,
                ).info("slack_connection_created")

            await db.commit()

            # Redirect to noyau.news with success message
            return RedirectResponse(
                url="https://noyau.news/?slack=success",
                status_code=status.HTTP_302_FOUND,
            )

        except Exception as e:
            await db.rollback()
            logger.bind(error=str(e)).error("slack_callback_error")
            return RedirectResponse(
                url=f"{settings.base_url}/?slack=error&message=internal_error",
                status_code=status.HTTP_302_FOUND,
            )


@router.get("/unsubscribe")
async def slack_unsubscribe(
    user_id: str = Query(..., description="Slack user ID"),
) -> RedirectResponse:
    """
    Unsubscribe from Slack digest DMs.

    Deactivates the connection.
    """
    settings = get_settings()

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MessagingConnection).where(
                MessagingConnection.platform == "slack",
                MessagingConnection.platform_user_id == user_id,
            )
        )
        connection = result.scalar_one_or_none()

        if connection:
            connection.is_active = False
            await db.commit()
            logger.bind(slack_user_id=user_id).info("slack_unsubscribed")

    return RedirectResponse(
        url=f"{settings.base_url}/?slack=unsubscribed",
        status_code=status.HTTP_302_FOUND,
    )
