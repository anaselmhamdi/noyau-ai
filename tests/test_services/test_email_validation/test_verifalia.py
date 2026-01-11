"""Tests for Verifalia email validator."""

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from app.services.email_validation import ValidationStatus
from app.services.email_validation.verifalia import VerifaliaValidator


class TestVerifaliaValidator:
    """Tests for VerifaliaValidator."""

    @pytest.fixture
    def validator(self):
        """Create a validator instance for testing."""
        return VerifaliaValidator(
            username="test-user",
            password="test-pass",
            quality="Standard",
            timeout_seconds=5,
            max_polls=3,
            poll_interval=0.1,
        )

    @pytest.fixture
    def mock_deliverable_response(self):
        """Mock response for a deliverable email."""
        return {
            "overview": {"id": "job-123", "status": "Completed"},
            "entries": [
                {
                    "inputData": "valid@example.com",
                    "classification": "Deliverable",
                    "status": "Success",
                    "isDisposableEmailAddress": False,
                    "isRoleAccount": False,
                    "isFreeEmailAddress": False,
                }
            ],
        }

    @pytest.fixture
    def mock_undeliverable_response(self):
        """Mock response for an undeliverable email."""
        return {
            "overview": {"id": "job-456", "status": "Completed"},
            "entries": [
                {
                    "inputData": "invalid@nonexistent.xyz",
                    "classification": "Undeliverable",
                    "status": "MailboxDoesNotExist",
                    "isDisposableEmailAddress": False,
                    "isRoleAccount": False,
                    "isFreeEmailAddress": False,
                }
            ],
        }

    @pytest.fixture
    def mock_risky_response(self):
        """Mock response for a risky (disposable) email."""
        return {
            "overview": {"id": "job-789", "status": "Completed"},
            "entries": [
                {
                    "inputData": "temp@mailinator.com",
                    "classification": "Risky",
                    "status": "DisposableEmailAddress",
                    "isDisposableEmailAddress": True,
                    "isRoleAccount": False,
                    "isFreeEmailAddress": True,
                }
            ],
        }

    @pytest.mark.asyncio
    async def test_validate_deliverable_email(self, validator, mock_deliverable_response):
        """Should return VALID for deliverable email."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session

            mock_post_response = AsyncMock()
            mock_post_response.status = 200
            mock_post_response.json = AsyncMock(return_value=mock_deliverable_response)
            mock_session.post.return_value.__aenter__.return_value = mock_post_response

            result = await validator.validate("valid@example.com")

            assert result.status == ValidationStatus.VALID
            assert result.is_deliverable is True
            assert result.is_disposable is False
            assert result.provider == "verifalia"

    @pytest.mark.asyncio
    async def test_validate_undeliverable_email(self, validator, mock_undeliverable_response):
        """Should return INVALID for undeliverable email."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session

            mock_post_response = AsyncMock()
            mock_post_response.status = 200
            mock_post_response.json = AsyncMock(return_value=mock_undeliverable_response)
            mock_session.post.return_value.__aenter__.return_value = mock_post_response

            result = await validator.validate("invalid@nonexistent.xyz")

            assert result.status == ValidationStatus.INVALID
            assert result.is_deliverable is False

    @pytest.mark.asyncio
    async def test_validate_disposable_email(self, validator, mock_risky_response):
        """Should return RISKY for disposable email."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session

            mock_post_response = AsyncMock()
            mock_post_response.status = 200
            mock_post_response.json = AsyncMock(return_value=mock_risky_response)
            mock_session.post.return_value.__aenter__.return_value = mock_post_response

            result = await validator.validate("temp@mailinator.com")

            assert result.status == ValidationStatus.RISKY
            assert result.is_disposable is True
            assert result.is_free_provider is True

    @pytest.mark.asyncio
    async def test_api_timeout_returns_unknown(self, validator):
        """Should return UNKNOWN on timeout (fail open)."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session
            mock_session.post.side_effect = TimeoutError("Connection timed out")

            result = await validator.validate("test@example.com")

            assert result.status == ValidationStatus.UNKNOWN
            assert result.is_deliverable is True  # Fail open
            # Error is caught and results in a generic failure message
            assert result.reason is not None

    @pytest.mark.asyncio
    async def test_api_error_returns_unknown(self, validator):
        """Should return UNKNOWN on API error."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session

            mock_post_response = AsyncMock()
            mock_post_response.status = 500
            mock_session.post.return_value.__aenter__.return_value = mock_post_response

            result = await validator.validate("test@example.com")

            assert result.status == ValidationStatus.UNKNOWN
            assert result.is_deliverable is True  # Fail open

    @pytest.mark.asyncio
    async def test_auth_failure_returns_unknown(self, validator):
        """Should return UNKNOWN on auth failure."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session

            mock_post_response = AsyncMock()
            mock_post_response.status = 401
            mock_session.post.return_value.__aenter__.return_value = mock_post_response

            result = await validator.validate("test@example.com")

            assert result.status == ValidationStatus.UNKNOWN
            assert result.is_deliverable is True

    @pytest.mark.asyncio
    async def test_client_error_returns_unknown(self, validator):
        """Should return UNKNOWN on client error."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session
            mock_session.post.side_effect = aiohttp.ClientError("Connection failed")

            result = await validator.validate("test@example.com")

            assert result.status == ValidationStatus.UNKNOWN
            assert result.is_deliverable is True

    @pytest.mark.asyncio
    async def test_polling_for_completion(self, validator, mock_deliverable_response):
        """Should poll for completion when job is not immediately ready."""
        # Response indicating job is still processing
        pending_response = {
            "overview": {"id": "job-123", "status": "InProgress"},
            "entries": [],
        }

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session

            # First POST returns accepted (202) with in-progress status
            mock_post_response = AsyncMock()
            mock_post_response.status = 202
            mock_post_response.json = AsyncMock(return_value=pending_response)
            mock_session.post.return_value.__aenter__.return_value = mock_post_response

            # GET returns completed after polling
            mock_get_response = AsyncMock()
            mock_get_response.status = 200
            mock_get_response.json = AsyncMock(return_value=mock_deliverable_response)
            mock_session.get.return_value.__aenter__.return_value = mock_get_response

            result = await validator.validate("valid@example.com")

            assert result.status == ValidationStatus.VALID
            # Verify polling happened
            assert mock_session.get.called

    @pytest.mark.asyncio
    async def test_validate_batch(self, validator):
        """Should validate multiple emails in batch."""
        batch_response = {
            "overview": {"id": "job-batch", "status": "Completed"},
            "entries": [
                {
                    "inputData": "valid@example.com",
                    "classification": "Deliverable",
                    "status": "Success",
                    "isDisposableEmailAddress": False,
                    "isRoleAccount": False,
                    "isFreeEmailAddress": False,
                },
                {
                    "inputData": "invalid@bad.xyz",
                    "classification": "Undeliverable",
                    "status": "MailboxDoesNotExist",
                    "isDisposableEmailAddress": False,
                    "isRoleAccount": False,
                    "isFreeEmailAddress": False,
                },
            ],
        }

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session

            mock_post_response = AsyncMock()
            mock_post_response.status = 200
            mock_post_response.json = AsyncMock(return_value=batch_response)
            mock_session.post.return_value.__aenter__.return_value = mock_post_response

            results = await validator.validate_batch(["valid@example.com", "invalid@bad.xyz"])

            assert len(results) == 2
            assert results[0].status == ValidationStatus.VALID
            assert results[1].status == ValidationStatus.INVALID


class TestVerifaliaValidatorShouldAllow:
    """Tests for should_allow policy method."""

    @pytest.fixture
    def validator(self):
        """Create a validator instance."""
        return VerifaliaValidator(username="test", password="test")

    def test_allows_valid_email(self, validator):
        """Should allow VALID emails."""
        from app.services.email_validation import ValidationResult

        result = ValidationResult(
            email="test@example.com",
            status=ValidationStatus.VALID,
            provider="verifalia",
            is_deliverable=True,
        )
        assert validator.should_allow(result) is True

    def test_allows_risky_email(self, validator):
        """Should allow RISKY emails (disposable, role-based)."""
        from app.services.email_validation import ValidationResult

        result = ValidationResult(
            email="temp@mailinator.com",
            status=ValidationStatus.RISKY,
            provider="verifalia",
            is_deliverable=True,
            is_disposable=True,
        )
        assert validator.should_allow(result) is True

    def test_allows_unknown_email(self, validator):
        """Should allow UNKNOWN emails (fail open)."""
        from app.services.email_validation import ValidationResult

        result = ValidationResult(
            email="test@example.com",
            status=ValidationStatus.UNKNOWN,
            provider="verifalia",
            is_deliverable=True,
        )
        assert validator.should_allow(result) is True

    def test_rejects_invalid_email(self, validator):
        """Should reject INVALID emails."""
        from app.services.email_validation import ValidationResult

        result = ValidationResult(
            email="bad@nonexistent.xyz",
            status=ValidationStatus.INVALID,
            provider="verifalia",
            is_deliverable=False,
        )
        assert validator.should_allow(result) is False
