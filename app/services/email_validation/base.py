"""Abstract base class for email validation providers."""

from abc import ABC, abstractmethod

from .models import ValidationResult, ValidationStatus


class BaseEmailValidator(ABC):
    """Abstract base class for email validation providers."""

    provider_name: str = "unknown"

    @abstractmethod
    async def validate(self, email: str) -> ValidationResult:
        """
        Validate a single email address.

        Args:
            email: The email address to validate

        Returns:
            ValidationResult with status and metadata
        """
        pass

    @abstractmethod
    async def validate_batch(self, emails: list[str]) -> list[ValidationResult]:
        """
        Validate multiple email addresses.

        Args:
            emails: List of email addresses

        Returns:
            List of ValidationResults in same order
        """
        pass

    def should_allow(self, result: ValidationResult) -> bool:
        """
        Determine if email should be allowed based on result.

        Default policy: Allow VALID, RISKY, and UNKNOWN (fail open).
        Only reject INVALID emails.
        """
        return result.status != ValidationStatus.INVALID
