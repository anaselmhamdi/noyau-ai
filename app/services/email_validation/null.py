"""Null validator - passthrough when validation is disabled."""

from .base import BaseEmailValidator
from .models import ValidationResult, ValidationStatus


class NullValidator(BaseEmailValidator):
    """
    Passthrough validator that always returns valid.

    Use when email validation is disabled or for testing.
    """

    provider_name = "null"

    async def validate(self, email: str) -> ValidationResult:
        """Always return valid result."""
        return ValidationResult(
            email=email,
            status=ValidationStatus.VALID,
            provider=self.provider_name,
            is_deliverable=True,
            reason="Validation disabled",
        )

    async def validate_batch(self, emails: list[str]) -> list[ValidationResult]:
        """Validate multiple emails (all valid)."""
        return [await self.validate(email) for email in emails]
