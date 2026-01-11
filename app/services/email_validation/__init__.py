"""Email validation service with provider abstraction."""

from app.config import get_settings

from .base import BaseEmailValidator
from .cached import CachedValidator
from .models import ValidationResult, ValidationStatus
from .null import NullValidator
from .verifalia import VerifaliaValidator

__all__ = [
    "BaseEmailValidator",
    "CachedValidator",
    "NullValidator",
    "ValidationResult",
    "ValidationStatus",
    "VerifaliaValidator",
    "get_email_validator",
]

_validator_instance: BaseEmailValidator | None = None


def get_email_validator() -> BaseEmailValidator:
    """
    Get the configured email validator instance.

    Uses singleton pattern for caching efficiency.
    Falls back to NullValidator if credentials not configured.
    """
    global _validator_instance
    if _validator_instance is not None:
        return _validator_instance

    settings = get_settings()

    if not settings.verifalia_username or not settings.verifalia_password:
        # Validation disabled - use passthrough
        _validator_instance = NullValidator()
    else:
        # Create Verifalia validator with cache
        verifalia = VerifaliaValidator(
            username=settings.verifalia_username,
            password=settings.verifalia_password,
            quality=settings.verifalia_quality,
            timeout_seconds=settings.verifalia_timeout,
        )
        _validator_instance = CachedValidator(
            verifalia,
            cache_ttl_hours=settings.verifalia_cache_ttl_hours,
        )

    return _validator_instance


def reset_email_validator() -> None:
    """Reset the validator instance. Useful for testing."""
    global _validator_instance
    _validator_instance = None
