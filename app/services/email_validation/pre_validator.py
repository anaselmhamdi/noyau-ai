"""Pre-validation layer for email addresses.

Performs free validation checks before calling paid services like Verifalia.
Catches obviously invalid emails to save API costs and block abuse.
"""

from pathlib import Path

from .base import BaseEmailValidator
from .models import ValidationResult, ValidationStatus

# RFC 2606 reserved domains + common test domains
RESERVED_DOMAINS = frozenset(
    {
        # RFC 2606 reserved
        "example.com",
        "example.org",
        "example.net",
        "example.edu",
        "test.com",
        "test.org",
        "test.net",
        "localhost",
        "localhost.localdomain",
        "invalid",
        # Common test patterns
        "example",
        "test",
        # Spam domains
        "testuser.dev",
    }
)

# Reserved TLDs that should never be used
RESERVED_TLDS = frozenset(
    {
        "test",
        "example",
        "invalid",
        "localhost",
    }
)


def _load_disposable_domains() -> frozenset[str]:
    """Load disposable domains from file into a frozenset for O(1) lookup."""
    domains_file = Path(__file__).parent / "disposable_domains.txt"
    if not domains_file.exists():
        return frozenset()

    domains = set()
    with open(domains_file) as f:
        for line in f:
            line = line.strip().lower()
            # Skip comments and empty lines
            if line and not line.startswith("#"):
                domains.add(line)
    return frozenset(domains)


# Load disposable domains once at module import
DISPOSABLE_DOMAINS = _load_disposable_domains()


class PreValidator(BaseEmailValidator):
    """
    Pre-validation layer that performs free checks before paid validation.

    Wraps another validator and only calls it if the email passes pre-checks.
    This saves API costs and blocks obvious abuse.
    """

    provider_name = "pre_validator"

    def __init__(self, validator: BaseEmailValidator) -> None:
        """
        Initialize PreValidator.

        Args:
            validator: The underlying validator to call if pre-checks pass
        """
        self._validator = validator

    async def validate(self, email: str) -> ValidationResult:
        """Validate email, rejecting obviously invalid ones before calling wrapped validator."""
        # Normalize
        email = email.strip().lower()

        # Check basic format
        if not self._is_valid_format(email):
            return self._invalid_result(email, "Invalid email format")

        # Extract domain
        domain = email.split("@")[1]

        # Check reserved domains
        if domain in RESERVED_DOMAINS:
            return self._invalid_result(email, f"Reserved domain: {domain}")

        # Check reserved TLDs
        tld = domain.split(".")[-1] if "." in domain else domain
        if tld in RESERVED_TLDS:
            return self._invalid_result(email, f"Reserved TLD: {tld}")

        # Check disposable domains
        if domain in DISPOSABLE_DOMAINS:
            return self._invalid_result(email, f"Disposable domain: {domain}")

        # All pre-checks passed, call wrapped validator
        return await self._validator.validate(email)

    async def validate_batch(self, emails: list[str]) -> list[ValidationResult]:
        """Validate multiple emails, filtering out invalid ones before calling wrapped validator."""
        results: list[ValidationResult | None] = [None] * len(emails)
        to_validate: list[str] = []
        to_validate_indices: list[int] = []

        for i, email in enumerate(emails):
            # Run pre-validation
            pre_result = await self.validate(email)

            # If pre-validation rejected it, use that result
            if pre_result.status == ValidationStatus.INVALID:
                results[i] = pre_result
            else:
                # Need to validate with wrapped validator
                to_validate.append(email)
                to_validate_indices.append(i)

        # Call wrapped validator for emails that passed pre-checks
        if to_validate:
            wrapped_results = await self._validator.validate_batch(to_validate)
            for idx, result in zip(to_validate_indices, wrapped_results):
                results[idx] = result

        return [r for r in results if r is not None]

    def _is_valid_format(self, email: str) -> bool:
        """Check basic email format."""
        # Must have exactly one @
        if email.count("@") != 1:
            return False

        local, domain = email.split("@")

        # Local part and domain must not be empty
        if not local or not domain:
            return False

        # Domain must have at least one dot (except for reserved TLDs we'll catch later)
        if "." not in domain and domain not in RESERVED_TLDS:
            return False

        return True

    def _invalid_result(self, email: str, reason: str) -> ValidationResult:
        """Create an INVALID result."""
        return ValidationResult(
            email=email,
            status=ValidationStatus.INVALID,
            provider=self.provider_name,
            is_deliverable=False,
            reason=reason,
        )

    def should_allow(self, result: ValidationResult) -> bool:
        """Delegate to underlying validator."""
        return self._validator.should_allow(result)
