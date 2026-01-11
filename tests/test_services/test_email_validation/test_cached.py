"""Tests for cached email validator."""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from app.core.datetime_utils import utc_now
from app.services.email_validation import ValidationResult, ValidationStatus
from app.services.email_validation.cached import CachedValidator


class TestCachedValidator:
    """Tests for CachedValidator."""

    @pytest.fixture
    def mock_validator(self):
        """Create a mock underlying validator."""
        mock = AsyncMock()
        mock.provider_name = "mock"
        mock.should_allow.return_value = True
        return mock

    @pytest.fixture
    def cached_validator(self, mock_validator):
        """Create a cached validator wrapping the mock."""
        return CachedValidator(mock_validator, cache_ttl_hours=1)

    @pytest.mark.asyncio
    async def test_caches_valid_results(self, cached_validator, mock_validator):
        """Should cache VALID results."""
        mock_validator.validate.return_value = ValidationResult(
            email="test@example.com",
            status=ValidationStatus.VALID,
            provider="mock",
            is_deliverable=True,
        )

        # First call - should hit the underlying validator
        result1 = await cached_validator.validate("test@example.com")
        assert result1.status == ValidationStatus.VALID
        assert mock_validator.validate.call_count == 1

        # Second call - should use cache
        result2 = await cached_validator.validate("test@example.com")
        assert result2.status == ValidationStatus.VALID
        assert mock_validator.validate.call_count == 1  # Not incremented

    @pytest.mark.asyncio
    async def test_does_not_cache_invalid_results(self, cached_validator, mock_validator):
        """Should not cache INVALID results."""
        mock_validator.validate.return_value = ValidationResult(
            email="invalid@bad.xyz",
            status=ValidationStatus.INVALID,
            provider="mock",
            is_deliverable=False,
        )

        # First call
        result1 = await cached_validator.validate("invalid@bad.xyz")
        assert result1.status == ValidationStatus.INVALID
        assert mock_validator.validate.call_count == 1

        # Second call - should NOT use cache (invalid not cached)
        result2 = await cached_validator.validate("invalid@bad.xyz")
        assert result2.status == ValidationStatus.INVALID
        assert mock_validator.validate.call_count == 2  # Incremented

    @pytest.mark.asyncio
    async def test_does_not_cache_risky_results(self, cached_validator, mock_validator):
        """Should not cache RISKY results."""
        mock_validator.validate.return_value = ValidationResult(
            email="temp@mailinator.com",
            status=ValidationStatus.RISKY,
            provider="mock",
            is_deliverable=True,
            is_disposable=True,
        )

        # First call
        await cached_validator.validate("temp@mailinator.com")
        assert mock_validator.validate.call_count == 1

        # Second call - should NOT use cache
        await cached_validator.validate("temp@mailinator.com")
        assert mock_validator.validate.call_count == 2

    @pytest.mark.asyncio
    async def test_does_not_cache_unknown_results(self, cached_validator, mock_validator):
        """Should not cache UNKNOWN results."""
        mock_validator.validate.return_value = ValidationResult(
            email="test@example.com",
            status=ValidationStatus.UNKNOWN,
            provider="mock",
            is_deliverable=True,
        )

        await cached_validator.validate("test@example.com")
        await cached_validator.validate("test@example.com")
        assert mock_validator.validate.call_count == 2

    @pytest.mark.asyncio
    async def test_cache_expiry(self, mock_validator):
        """Should expire cached results after TTL."""
        # Use very short TTL for testing
        cached_validator = CachedValidator(mock_validator, cache_ttl_hours=0)
        # Manually set TTL to 0 seconds for immediate expiry
        cached_validator._ttl = timedelta(seconds=0)

        mock_validator.validate.return_value = ValidationResult(
            email="test@example.com",
            status=ValidationStatus.VALID,
            provider="mock",
            is_deliverable=True,
        )

        # First call
        await cached_validator.validate("test@example.com")
        assert mock_validator.validate.call_count == 1

        # Second call - cache should be expired
        await cached_validator.validate("test@example.com")
        assert mock_validator.validate.call_count == 2

    @pytest.mark.asyncio
    async def test_cache_key_is_case_insensitive(self, cached_validator, mock_validator):
        """Cache key should be case-insensitive."""
        mock_validator.validate.return_value = ValidationResult(
            email="Test@Example.com",
            status=ValidationStatus.VALID,
            provider="mock",
            is_deliverable=True,
        )

        await cached_validator.validate("Test@Example.com")
        await cached_validator.validate("test@example.com")
        await cached_validator.validate("TEST@EXAMPLE.COM")

        # All should use the same cache entry
        assert mock_validator.validate.call_count == 1

    @pytest.mark.asyncio
    async def test_batch_uses_cache(self, cached_validator, mock_validator):
        """Batch validation should use cache for hits."""
        # Pre-populate cache with a valid result
        mock_validator.validate.return_value = ValidationResult(
            email="cached@example.com",
            status=ValidationStatus.VALID,
            provider="mock",
            is_deliverable=True,
        )
        await cached_validator.validate("cached@example.com")
        assert mock_validator.validate.call_count == 1

        # Setup batch validation
        mock_validator.validate_batch.return_value = [
            ValidationResult(
                email="new@example.com",
                status=ValidationStatus.VALID,
                provider="mock",
                is_deliverable=True,
            )
        ]

        # Batch with one cached and one new
        results = await cached_validator.validate_batch(["cached@example.com", "new@example.com"])

        assert len(results) == 2
        # Only the new email should have been validated
        mock_validator.validate_batch.assert_called_once_with(["new@example.com"])

    @pytest.mark.asyncio
    async def test_batch_all_cached(self, cached_validator, mock_validator):
        """Batch with all cached emails should not call validator."""
        mock_validator.validate.return_value = ValidationResult(
            email="cached@example.com",
            status=ValidationStatus.VALID,
            provider="mock",
            is_deliverable=True,
        )

        # Pre-populate cache
        await cached_validator.validate("email1@example.com")
        await cached_validator.validate("email2@example.com")

        # Batch with all cached
        results = await cached_validator.validate_batch(
            ["email1@example.com", "email2@example.com"]
        )

        assert len(results) == 2
        # validate_batch should not have been called
        mock_validator.validate_batch.assert_not_called()

    def test_provider_name(self, cached_validator, mock_validator):
        """Provider name should indicate caching."""
        assert cached_validator.provider_name == "cached:mock"

    def test_clear_cache(self, cached_validator):
        """Should be able to clear the cache."""
        cached_validator._cache["test@example.com"] = (
            ValidationResult(
                email="test@example.com",
                status=ValidationStatus.VALID,
                provider="mock",
                is_deliverable=True,
            ),
            utc_now(),
        )

        assert cached_validator.cache_size() == 1
        cached_validator.clear_cache()
        assert cached_validator.cache_size() == 0

    def test_should_allow_delegates_to_underlying(self, mock_validator):
        """should_allow should delegate to underlying validator."""
        from unittest.mock import MagicMock

        # Create a mock with sync should_allow
        sync_mock = MagicMock()
        sync_mock.provider_name = "mock"
        cached = CachedValidator(sync_mock, cache_ttl_hours=1)

        result = ValidationResult(
            email="test@example.com",
            status=ValidationStatus.VALID,
            provider="mock",
            is_deliverable=True,
        )

        sync_mock.should_allow.return_value = True
        assert cached.should_allow(result) is True
        sync_mock.should_allow.assert_called_once_with(result)

        sync_mock.should_allow.return_value = False
        assert cached.should_allow(result) is False
