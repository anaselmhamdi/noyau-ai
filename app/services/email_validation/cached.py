"""Cached email validator decorator."""

from datetime import datetime, timedelta

from app.core.datetime_utils import utc_now

from .base import BaseEmailValidator
from .models import ValidationResult, ValidationStatus


class CachedValidator(BaseEmailValidator):
    """
    Decorator that caches validation results to reduce API calls.

    Only caches VALID results (invalid emails may become valid later).
    """

    def __init__(
        self,
        validator: BaseEmailValidator,
        cache_ttl_hours: int = 24,
    ) -> None:
        """
        Initialize cached validator.

        Args:
            validator: The underlying validator to wrap
            cache_ttl_hours: How long to cache valid results
        """
        self._validator = validator
        self._cache: dict[str, tuple[ValidationResult, datetime]] = {}
        self._ttl = timedelta(hours=cache_ttl_hours)

    @property
    def provider_name(self) -> str:  # type: ignore[override]
        """Return combined provider name."""
        return f"cached:{self._validator.provider_name}"

    async def validate(self, email: str) -> ValidationResult:
        """Validate email, using cache if available."""
        # Normalize email for cache key
        cache_key = email.lower().strip()

        # Check cache
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        # Call underlying validator
        result = await self._validator.validate(email)

        # Only cache valid results
        if result.status == ValidationStatus.VALID:
            self._cache[cache_key] = (result, utc_now())

        return result

    async def validate_batch(self, emails: list[str]) -> list[ValidationResult]:
        """Validate multiple emails, using cache where possible."""
        results: list[ValidationResult | None] = []
        to_validate: list[str] = []
        to_validate_indices: list[int] = []

        # Check cache for each email
        for i, email in enumerate(emails):
            cache_key = email.lower().strip()
            cached = self._get_cached(cache_key)
            if cached:
                results.append(cached)
            else:
                results.append(None)
                to_validate.append(email)
                to_validate_indices.append(i)

        # Fetch uncached emails
        if to_validate:
            fresh_results = await self._validator.validate_batch(to_validate)
            for idx, result in zip(to_validate_indices, fresh_results):
                results[idx] = result
                # Cache valid results
                if result.status == ValidationStatus.VALID:
                    cache_key = result.email.lower().strip()
                    self._cache[cache_key] = (result, utc_now())

        # Type assertion - all None values should be filled
        return [r for r in results if r is not None]

    def _get_cached(self, cache_key: str) -> ValidationResult | None:
        """Get cached result if not expired."""
        cached = self._cache.get(cache_key)
        if cached:
            result, cached_at = cached
            if utc_now() - cached_at < self._ttl:
                return result
            # Expired - remove from cache
            del self._cache[cache_key]
        return None

    def clear_cache(self) -> None:
        """Clear all cached results."""
        self._cache.clear()

    def cache_size(self) -> int:
        """Return current cache size."""
        return len(self._cache)

    def should_allow(self, result: ValidationResult) -> bool:
        """Delegate to underlying validator."""
        return self._validator.should_allow(result)
