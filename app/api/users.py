from fastapi import APIRouter

from app.dependencies import CurrentUserOptional
from app.schemas.auth import MeResponse

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
        ref_code=user.ref_code,
    )
