"""Email validation models."""

from enum import Enum

from pydantic import BaseModel


class ValidationStatus(str, Enum):
    """Result status of email validation."""

    VALID = "valid"  # Deliverable
    INVALID = "invalid"  # Undeliverable (bad syntax, no MX, mailbox doesn't exist)
    RISKY = "risky"  # Catch-all, disposable, role-based
    UNKNOWN = "unknown"  # Could not determine (timeout, API error)


class ValidationResult(BaseModel):
    """Result of email validation."""

    email: str
    status: ValidationStatus
    provider: str
    is_deliverable: bool
    is_disposable: bool = False
    is_role_based: bool = False
    is_free_provider: bool = False
    reason: str | None = None
    raw_response: dict | None = None
