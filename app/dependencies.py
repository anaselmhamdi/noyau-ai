import uuid
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.config import AppConfig, Settings, get_config, get_settings
from app.core.database import get_db
from app.core.security import is_expired
from app.models.user import Session, User

# Type aliases for dependency injection
DBSession = Annotated[AsyncSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]
Config = Annotated[AppConfig, Depends(get_config)]


async def get_current_user_optional(
    db: DBSession,
    session_id: str | None = Cookie(default=None, alias="session_id"),
) -> User | None:
    """Get the current user if authenticated, None otherwise."""
    if not session_id:
        return None

    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        return None

    result = await db.execute(
        select(Session).where(Session.id == session_uuid).options(joinedload(Session.user))
    )
    session = result.scalar_one_or_none()

    if not session:
        return None

    if is_expired(session.expires_at):
        # Clean up expired session
        await db.delete(session)
        return None

    user: User = session.user
    return user


async def get_current_user(
    user: User | None = Depends(get_current_user_optional),
) -> User:
    """Get the current user, raise 401 if not authenticated."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user


# Type aliases for authenticated endpoints
CurrentUserOptional = Annotated[User | None, Depends(get_current_user_optional)]
CurrentUser = Annotated[User, Depends(get_current_user)]
