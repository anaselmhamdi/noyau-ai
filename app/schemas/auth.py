from pydantic import BaseModel, EmailStr, Field, field_validator


class MagicLinkRequest(BaseModel):
    """Request body for magic link generation."""

    email: EmailStr
    redirect: str = Field(default="/", max_length=255)
    timezone: str | None = Field(default=None, max_length=50)
    delivery_time_local: str | None = Field(default=None, max_length=5)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        from app.core.datetime_utils import is_valid_timezone

        if not is_valid_timezone(v):
            return None  # Fall back to default instead of raising error
        return v

    @field_validator("delivery_time_local")
    @classmethod
    def validate_delivery_time(cls, v: str | None) -> str | None:
        if v is None:
            return v
        # Validate HH:MM format
        try:
            parts = v.split(":")
            if len(parts) != 2:
                return None
            hour, minute = int(parts[0]), int(parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return None
            return f"{hour:02d}:{minute:02d}"
        except (ValueError, IndexError):
            return None


class MagicLinkResponse(BaseModel):
    """Response after requesting a magic link."""

    ok: bool = True
    message: str = "Magic link sent to your email"


class MeResponse(BaseModel):
    """Response for /api/me endpoint."""

    authed: bool
    email: str | None = None
    timezone: str | None = None
    delivery_time_local: str | None = None
    ref_code: str | None = None
    is_subscribed: bool | None = None


class UserPreferencesUpdate(BaseModel):
    """Request body for updating user preferences."""

    timezone: str | None = Field(default=None, max_length=50)
    delivery_time_local: str | None = Field(default=None, max_length=5)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        from app.core.datetime_utils import is_valid_timezone

        if not is_valid_timezone(v):
            raise ValueError(f"Invalid timezone: {v}")
        return v

    @field_validator("delivery_time_local")
    @classmethod
    def validate_delivery_time(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            parts = v.split(":")
            if len(parts) != 2:
                raise ValueError("Time must be in HH:MM format")
            hour, minute = int(parts[0]), int(parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Invalid hour or minute")
            return f"{hour:02d}:{minute:02d}"
        except (ValueError, IndexError) as e:
            raise ValueError(f"Invalid time format: {e}") from e
