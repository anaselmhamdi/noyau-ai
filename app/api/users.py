from fastapi import APIRouter

from app.core.datetime_utils import COMMON_TIMEZONES
from app.dependencies import CurrentUser, CurrentUserOptional, DBSession
from app.schemas.auth import MeResponse, UserPreferencesUpdate

router = APIRouter()


@router.get("/me", response_model=MeResponse)
async def get_current_user_info(
    user: CurrentUserOptional,
) -> MeResponse:
    """
    Get current user information.

    Returns authed=false if not logged in, otherwise returns user details.
    """
    if not user:
        return MeResponse(authed=False)

    return MeResponse(
        authed=True,
        email=user.email,
        timezone=user.timezone,
        delivery_time_local=user.delivery_time_local,
        ref_code=user.ref_code,
        is_subscribed=user.is_subscribed,
    )


@router.patch("/me/preferences", response_model=MeResponse)
async def update_user_preferences(
    preferences: UserPreferencesUpdate,
    user: CurrentUser,
    db: DBSession,
) -> MeResponse:
    """
    Update current user's timezone and delivery preferences.

    Args:
        preferences: The preferences to update (timezone, delivery_time_local)

    Returns:
        Updated user information
    """
    # Update timezone if provided
    if preferences.timezone is not None:
        user.timezone = preferences.timezone

    # Update delivery time if provided
    if preferences.delivery_time_local is not None:
        user.delivery_time_local = preferences.delivery_time_local

    await db.commit()
    await db.refresh(user)

    return MeResponse(
        authed=True,
        email=user.email,
        timezone=user.timezone,
        delivery_time_local=user.delivery_time_local,
        ref_code=user.ref_code,
        is_subscribed=user.is_subscribed,
    )


@router.get("/timezones")
async def get_timezones() -> dict:
    """
    Get list of common timezones for UI dropdown.

    Returns:
        Dict with common_timezones list
    """
    return {"timezones": COMMON_TIMEZONES}


@router.post("/me/unsubscribe")
async def unsubscribe_current_user(
    user: CurrentUser,
    db: DBSession,
) -> dict:
    """
    Unsubscribe current user from email digests.

    Returns:
        Confirmation message
    """
    user.is_subscribed = False
    await db.commit()

    return {"ok": True, "message": "You have been unsubscribed from email digests."}


@router.post("/me/resubscribe")
async def resubscribe_current_user(
    user: CurrentUser,
    db: DBSession,
) -> dict:
    """
    Resubscribe current user to email digests.

    Returns:
        Confirmation message
    """
    user.is_subscribed = True
    await db.commit()

    return {"ok": True, "message": "You have been resubscribed to email digests."}
