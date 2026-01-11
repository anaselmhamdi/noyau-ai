from pydantic import BaseModel, EmailStr, Field


class MagicLinkRequest(BaseModel):
    """Request body for magic link generation."""

    email: EmailStr
    redirect: str = Field(default="/", max_length=255)


class MagicLinkResponse(BaseModel):
    """Response after requesting a magic link."""

    ok: bool = True
    message: str = "Magic link sent to your email"


class MeResponse(BaseModel):
    """Response for /api/me endpoint."""

    authed: bool
    email: str | None = None
    timezone: str | None = None
    ref_code: str | None = None
