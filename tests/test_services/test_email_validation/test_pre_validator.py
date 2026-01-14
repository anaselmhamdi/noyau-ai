"""Tests for pre-validation email validator."""

from unittest.mock import AsyncMock

import pytest

from app.services.email_validation import ValidationResult, ValidationStatus
from app.services.email_validation.pre_validator import (
    DISPOSABLE_DOMAINS,
    RESERVED_DOMAINS,
    RESERVED_TLDS,
    PreValidator,
)


class TestPreValidator:
    """Tests for PreValidator."""

    @pytest.fixture
    def mock_validator(self):
        """Create a mock underlying validator."""
        mock = AsyncMock()
        mock.provider_name = "mock"
        mock.should_allow.return_value = True
        mock.validate.return_value = ValidationResult(
            email="valid@gmail.com",
            status=ValidationStatus.VALID,
            provider="mock",
            is_deliverable=True,
        )
        return mock

    @pytest.fixture
    def pre_validator(self, mock_validator):
        """Create a PreValidator wrapping the mock."""
        return PreValidator(mock_validator)

    # -------------------------------------------------------------------------
    # Reserved Domain Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_rejects_example_com(self, pre_validator, mock_validator):
        """Should reject example.com (RFC 2606 reserved)."""
        result = await pre_validator.validate("test@example.com")

        assert result.status == ValidationStatus.INVALID
        assert "Reserved domain" in result.reason
        mock_validator.validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_example_org(self, pre_validator, mock_validator):
        """Should reject example.org (RFC 2606 reserved)."""
        result = await pre_validator.validate("user@example.org")

        assert result.status == ValidationStatus.INVALID
        assert "Reserved domain" in result.reason
        mock_validator.validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_test_com(self, pre_validator, mock_validator):
        """Should reject test.com (reserved test domain)."""
        result = await pre_validator.validate("new@test.com")

        assert result.status == ValidationStatus.INVALID
        mock_validator.validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_localhost(self, pre_validator, mock_validator):
        """Should reject localhost."""
        result = await pre_validator.validate("admin@localhost")

        assert result.status == ValidationStatus.INVALID
        mock_validator.validate.assert_not_called()

    # -------------------------------------------------------------------------
    # Reserved TLD Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_rejects_test_tld(self, pre_validator, mock_validator):
        """Should reject .test TLD."""
        result = await pre_validator.validate("user@domain.test")

        assert result.status == ValidationStatus.INVALID
        assert "Reserved TLD" in result.reason
        mock_validator.validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_invalid_tld(self, pre_validator, mock_validator):
        """Should reject .invalid TLD."""
        result = await pre_validator.validate("user@domain.invalid")

        assert result.status == ValidationStatus.INVALID
        mock_validator.validate.assert_not_called()

    # -------------------------------------------------------------------------
    # Disposable Domain Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_rejects_mailinator(self, pre_validator, mock_validator):
        """Should reject mailinator.com (disposable)."""
        result = await pre_validator.validate("temp@mailinator.com")

        assert result.status == ValidationStatus.INVALID
        assert "Disposable domain" in result.reason
        mock_validator.validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_10minutemail(self, pre_validator, mock_validator):
        """Should reject 10minutemail.com (disposable)."""
        result = await pre_validator.validate("temp@10minutemail.com")

        assert result.status == ValidationStatus.INVALID
        mock_validator.validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_guerrillamail(self, pre_validator, mock_validator):
        """Should reject guerrillamail.com (disposable)."""
        result = await pre_validator.validate("temp@guerrillamail.com")

        assert result.status == ValidationStatus.INVALID
        mock_validator.validate.assert_not_called()

    # -------------------------------------------------------------------------
    # Invalid Format Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_rejects_no_at_sign(self, pre_validator, mock_validator):
        """Should reject emails without @."""
        result = await pre_validator.validate("notanemail")

        assert result.status == ValidationStatus.INVALID
        assert "Invalid email format" in result.reason
        mock_validator.validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_multiple_at_signs(self, pre_validator, mock_validator):
        """Should reject emails with multiple @."""
        result = await pre_validator.validate("bad@@domain.com")

        assert result.status == ValidationStatus.INVALID
        mock_validator.validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_empty_local_part(self, pre_validator, mock_validator):
        """Should reject emails with empty local part."""
        result = await pre_validator.validate("@domain.com")

        assert result.status == ValidationStatus.INVALID
        mock_validator.validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_empty_domain(self, pre_validator, mock_validator):
        """Should reject emails with empty domain."""
        result = await pre_validator.validate("user@")

        assert result.status == ValidationStatus.INVALID
        mock_validator.validate.assert_not_called()

    # -------------------------------------------------------------------------
    # Valid Email Tests (Should Pass Through)
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_allows_gmail(self, pre_validator, mock_validator):
        """Should allow gmail.com and call wrapped validator."""
        result = await pre_validator.validate("user@gmail.com")

        assert result.status == ValidationStatus.VALID
        mock_validator.validate.assert_called_once_with("user@gmail.com")

    @pytest.mark.asyncio
    async def test_allows_corporate_domain(self, pre_validator, mock_validator):
        """Should allow corporate domains and call wrapped validator."""
        result = await pre_validator.validate("john.doe@company.com")

        assert result.status == ValidationStatus.VALID
        mock_validator.validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_normalizes_email_case(self, pre_validator, mock_validator):
        """Should normalize email to lowercase before validation."""
        await pre_validator.validate("User@GMAIL.COM")

        mock_validator.validate.assert_called_once_with("user@gmail.com")

    @pytest.mark.asyncio
    async def test_strips_whitespace(self, pre_validator, mock_validator):
        """Should strip whitespace from email."""
        await pre_validator.validate("  user@gmail.com  ")

        mock_validator.validate.assert_called_once_with("user@gmail.com")

    # -------------------------------------------------------------------------
    # Batch Validation Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_batch_filters_invalid(self, pre_validator, mock_validator):
        """Batch should filter out invalid emails before calling wrapped validator."""
        mock_validator.validate_batch.return_value = [
            ValidationResult(
                email="valid@gmail.com",
                status=ValidationStatus.VALID,
                provider="mock",
                is_deliverable=True,
            )
        ]

        results = await pre_validator.validate_batch(
            [
                "test@example.com",  # Reserved - should be filtered
                "valid@gmail.com",  # Valid - should pass through
                "temp@mailinator.com",  # Disposable - should be filtered
            ]
        )

        assert len(results) == 3
        # First and third should be INVALID from pre-validator
        assert results[0].status == ValidationStatus.INVALID
        assert results[2].status == ValidationStatus.INVALID
        # Second should be from wrapped validator
        assert results[1].status == ValidationStatus.VALID
        # Only valid@gmail.com should have been sent to wrapped validator
        mock_validator.validate_batch.assert_called_once_with(["valid@gmail.com"])

    @pytest.mark.asyncio
    async def test_batch_all_invalid(self, pre_validator, mock_validator):
        """Batch with all invalid emails should not call wrapped validator."""
        results = await pre_validator.validate_batch(
            [
                "test@example.com",
                "temp@mailinator.com",
            ]
        )

        assert len(results) == 2
        assert all(r.status == ValidationStatus.INVALID for r in results)
        mock_validator.validate_batch.assert_not_called()

    # -------------------------------------------------------------------------
    # Delegation Tests
    # -------------------------------------------------------------------------

    def test_provider_name(self, pre_validator):
        """Provider name should be pre_validator."""
        assert pre_validator.provider_name == "pre_validator"

    def test_should_allow_delegates(self):
        """should_allow should delegate to underlying validator."""
        from unittest.mock import MagicMock

        # Create sync mock for should_allow (it's not async)
        sync_mock = MagicMock()
        sync_mock.provider_name = "mock"
        pre_val = PreValidator(sync_mock)

        result = ValidationResult(
            email="test@gmail.com",
            status=ValidationStatus.VALID,
            provider="mock",
            is_deliverable=True,
        )

        sync_mock.should_allow.return_value = True
        assert pre_val.should_allow(result) is True
        sync_mock.should_allow.assert_called_once_with(result)

    # -------------------------------------------------------------------------
    # Domain List Tests
    # -------------------------------------------------------------------------

    def test_reserved_domains_loaded(self):
        """Reserved domains should be loaded."""
        assert "example.com" in RESERVED_DOMAINS
        assert "test.com" in RESERVED_DOMAINS
        assert "localhost" in RESERVED_DOMAINS

    def test_reserved_tlds_loaded(self):
        """Reserved TLDs should be loaded."""
        assert "test" in RESERVED_TLDS
        assert "invalid" in RESERVED_TLDS
        assert "localhost" in RESERVED_TLDS

    def test_disposable_domains_loaded(self):
        """Disposable domains should be loaded from file."""
        # Should have many domains loaded
        assert len(DISPOSABLE_DOMAINS) > 1000
        # Should include common disposable domains
        assert "mailinator.com" in DISPOSABLE_DOMAINS
        assert "10minutemail.com" in DISPOSABLE_DOMAINS
