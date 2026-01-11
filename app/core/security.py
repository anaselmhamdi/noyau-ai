import hashlib
import hmac
import secrets
import uuid

from app.config import get_settings
from app.core.datetime_utils import get_expiry, is_expired

settings = get_settings()


def generate_token() -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash a token for storage using SHA-256."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_ref_code() -> str:
    """Generate a short unique referral code."""
    return secrets.token_urlsafe(8)


def generate_session_id() -> uuid.UUID:
    """Generate a new session ID."""
    return uuid.uuid4()


def get_magic_link_expiry():
    """Get expiry time for magic links (15 minutes from now)."""
    return get_expiry(minutes=15)


def get_session_expiry():
    """Get expiry time for sessions (30 days from now)."""
    return get_expiry(days=30)


# Re-export is_expired from datetime_utils for backwards compatibility
__all__ = ["is_expired"]


def build_magic_link_url(token: str, redirect_path: str = "/") -> str:
    """Build the full magic link URL."""
    return f"{settings.base_url}/auth/magic?token={token}&redirect={redirect_path}"


def generate_unsubscribe_token(email: str) -> str:
    """Generate HMAC token for unsubscribe link."""
    secret = settings.secret_key.encode()
    return hmac.new(secret, email.lower().encode(), hashlib.sha256).hexdigest()[:32]


def verify_unsubscribe_token(email: str, token: str) -> bool:
    """Verify unsubscribe token matches email."""
    expected = generate_unsubscribe_token(email)
    return hmac.compare_digest(expected, token)
