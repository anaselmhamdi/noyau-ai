"""Integration tests for email validation with auth endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.services.email_validation import ValidationResult, ValidationStatus


class TestAuthEmailValidation:
    """Test email validation integration with auth endpoint."""

    @pytest.mark.asyncio
    async def test_request_link_validates_email(self, client: AsyncClient):
        """POST /auth/request-link should validate email before creating magic link."""
        from unittest.mock import MagicMock

        mock_validator = MagicMock()
        mock_validator.validate = AsyncMock(
            return_value=ValidationResult(
                email="test@example.com",
                status=ValidationStatus.VALID,
                provider="mock",
                is_deliverable=True,
            )
        )
        mock_validator.should_allow.return_value = True

        with (
            patch("app.api.auth.get_email_validator", return_value=mock_validator),
            patch("app.api.auth.send_magic_link_email", new_callable=AsyncMock),
        ):
            response = await client.post(
                "/auth/request-link",
                json={"email": "test@example.com"},
            )

        assert response.status_code == 200
        mock_validator.validate.assert_called_once_with("test@example.com")
        mock_validator.should_allow.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_link_rejects_invalid_email(self, client: AsyncClient):
        """Should reject invalid emails with 400."""
        from unittest.mock import MagicMock

        # Create mock with sync should_allow
        mock_validator = MagicMock()
        mock_validator.validate = AsyncMock(
            return_value=ValidationResult(
                email="bad@invalid.xyz",
                status=ValidationStatus.INVALID,
                provider="mock",
                is_deliverable=False,
                reason="MailboxDoesNotExist",
            )
        )
        mock_validator.should_allow.return_value = False

        with patch("app.api.auth.get_email_validator", return_value=mock_validator):
            response = await client.post(
                "/auth/request-link",
                json={"email": "bad@invalid.xyz"},
            )

        assert response.status_code == 400
        data = response.json()
        assert "valid email" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_request_link_allows_risky_email(self, client: AsyncClient):
        """Should allow risky (disposable) emails but log them."""
        from unittest.mock import MagicMock

        mock_validator = MagicMock()
        mock_validator.validate = AsyncMock(
            return_value=ValidationResult(
                email="temp@mailinator.com",
                status=ValidationStatus.RISKY,
                provider="mock",
                is_deliverable=True,
                is_disposable=True,
            )
        )
        mock_validator.should_allow.return_value = True

        with (
            patch("app.api.auth.get_email_validator", return_value=mock_validator),
            patch("app.api.auth.send_magic_link_email", new_callable=AsyncMock),
        ):
            response = await client.post(
                "/auth/request-link",
                json={"email": "temp@mailinator.com"},
            )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_request_link_allows_unknown_email(self, client: AsyncClient):
        """Should allow unknown emails (fail open on API errors)."""
        from unittest.mock import MagicMock

        mock_validator = MagicMock()
        mock_validator.validate = AsyncMock(
            return_value=ValidationResult(
                email="test@example.com",
                status=ValidationStatus.UNKNOWN,
                provider="mock",
                is_deliverable=True,
                reason="API timeout",
            )
        )
        mock_validator.should_allow.return_value = True

        with (
            patch("app.api.auth.get_email_validator", return_value=mock_validator),
            patch("app.api.auth.send_magic_link_email", new_callable=AsyncMock),
        ):
            response = await client.post(
                "/auth/request-link",
                json={"email": "test@example.com"},
            )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_request_link_still_validates_syntax(self, client: AsyncClient):
        """Pydantic should still validate email syntax before our validator."""
        # Invalid email syntax should fail Pydantic validation first
        response = await client.post(
            "/auth/request-link",
            json={"email": "not-an-email"},
        )

        assert response.status_code == 422  # Validation error


class TestNullValidator:
    """Test that NullValidator is used when credentials not configured."""

    @pytest.mark.asyncio
    async def test_null_validator_always_valid(self):
        """NullValidator should always return valid."""
        from app.services.email_validation.null import NullValidator

        validator = NullValidator()
        result = await validator.validate("any@email.com")

        assert result.status == ValidationStatus.VALID
        assert result.is_deliverable is True
        assert result.provider == "null"

    @pytest.mark.asyncio
    async def test_null_validator_batch(self):
        """NullValidator batch should return all valid."""
        from app.services.email_validation.null import NullValidator

        validator = NullValidator()
        results = await validator.validate_batch(["a@b.com", "c@d.com", "e@f.com"])

        assert len(results) == 3
        assert all(r.status == ValidationStatus.VALID for r in results)


class TestEmailValidatorFactory:
    """Test the email validator factory function."""

    def test_returns_pre_validator_when_no_credentials(self):
        """Should return PreValidator wrapping NullValidator when Verifalia credentials missing."""
        from app.services.email_validation import reset_email_validator
        from app.services.email_validation.pre_validator import PreValidator

        # Reset singleton
        reset_email_validator()

        with patch("app.services.email_validation.get_settings") as mock_settings:
            mock_settings.return_value.verifalia_username = ""
            mock_settings.return_value.verifalia_password = ""

            from app.services.email_validation import get_email_validator

            validator = get_email_validator()

            # Without credentials, returns PreValidator wrapping NullValidator
            assert isinstance(validator, PreValidator)
            assert validator.provider_name == "pre_validator"

        # Reset again for other tests
        reset_email_validator()

    def test_returns_cached_pre_validator_verifalia_when_credentials_present(self):
        """Should return CachedValidator wrapping PreValidator wrapping Verifalia."""
        from app.services.email_validation import reset_email_validator
        from app.services.email_validation.cached import CachedValidator

        # Reset singleton
        reset_email_validator()

        with patch("app.services.email_validation.get_settings") as mock_settings:
            mock_settings.return_value.verifalia_username = "test-user"
            mock_settings.return_value.verifalia_password = "test-pass"
            mock_settings.return_value.verifalia_quality = "Standard"
            mock_settings.return_value.verifalia_timeout = 30
            mock_settings.return_value.verifalia_cache_ttl_hours = 24

            from app.services.email_validation import get_email_validator

            validator = get_email_validator()

            # Chain: CachedValidator -> PreValidator -> VerifaliaValidator
            assert isinstance(validator, CachedValidator)
            assert "pre_validator" in validator.provider_name

        # Reset for other tests
        reset_email_validator()
