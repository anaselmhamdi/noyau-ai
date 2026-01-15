"""Tests for authentication endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestRequestMagicLink:
    """Tests for POST /auth/request-link."""

    async def test_request_link_success(self, client: AsyncClient):
        """Should return ok when requesting magic link."""
        response = await client.post(
            "/auth/request-link",
            json={"email": "test@gmail.com", "redirect": "/daily/2026-01-10"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "message" in data

    async def test_request_link_invalid_email(self, client: AsyncClient):
        """Should reject invalid email addresses."""
        response = await client.post(
            "/auth/request-link",
            json={"email": "not-an-email", "redirect": "/"},
        )

        assert response.status_code == 422  # Validation error

    async def test_request_link_default_redirect(self, client: AsyncClient):
        """Should use default redirect when not specified."""
        response = await client.post(
            "/auth/request-link",
            json={"email": "test@gmail.com"},
        )

        assert response.status_code == 200

    async def test_request_link_rejects_reserved_domain(self, client: AsyncClient):
        """Should reject emails with reserved domains like example.com."""
        response = await client.post(
            "/auth/request-link",
            json={"email": "test@example.com", "redirect": "/"},
        )

        assert response.status_code == 400
        assert "valid email" in response.json()["detail"].lower()

    async def test_request_link_rejects_disposable_domain(self, client: AsyncClient):
        """Should reject emails with disposable domains like mailinator.com."""
        response = await client.post(
            "/auth/request-link",
            json={"email": "temp@mailinator.com", "redirect": "/"},
        )

        assert response.status_code == 400
        assert "valid email" in response.json()["detail"].lower()


class TestSubscribe:
    """Tests for POST /auth/subscribe (optimistic flow)."""

    @patch("app.api.auth._process_subscription", new_callable=AsyncMock)
    async def test_subscribe_returns_immediately(
        self, mock_process: AsyncMock, client: AsyncClient
    ):
        """Should return ok and redirect without waiting for validation."""
        response = await client.post(
            "/auth/subscribe",
            json={
                "email": "newuser@gmail.com",
                "timezone": "America/New_York",
                "delivery_time_local": "08:00",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["redirect"] == "/welcome"
        # No session cookie in optimistic flow
        assert "session_id" not in response.cookies
        # Background task was queued
        mock_process.assert_called_once_with(
            email="newuser@gmail.com",
            timezone="America/New_York",
            delivery_time_local="08:00",
        )

    async def test_subscribe_invalid_email_format(self, client: AsyncClient):
        """Should reject malformed email addresses."""
        response = await client.post(
            "/auth/subscribe",
            json={"email": "not-an-email"},
        )

        assert response.status_code == 422  # Pydantic validation error

    @patch("app.api.auth._process_subscription", new_callable=AsyncMock)
    async def test_subscribe_with_defaults(self, mock_process: AsyncMock, client: AsyncClient):
        """Should work with just email, using defaults for timezone/time."""
        response = await client.post(
            "/auth/subscribe",
            json={"email": "minimal@gmail.com"},
        )

        assert response.status_code == 200
        assert response.json()["ok"] is True


class TestVerifyMagicLink:
    """Tests for GET /auth/magic."""

    async def test_verify_valid_token_new_user(
        self, client: AsyncClient, magic_link_factory, db_session
    ):
        """Should create user and session for valid token."""
        magic_link, token = await magic_link_factory(
            email="new@testuser.dev",
            redirect_path="/daily/2026-01-10",
        )

        response = await client.get(
            "/auth/magic",
            params={"token": token, "redirect": "/daily/2026-01-10"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["location"] == "/daily/2026-01-10"
        assert "session_id" in response.cookies

    async def test_verify_valid_token_existing_user(
        self, client: AsyncClient, magic_link_factory, user_factory, db_session
    ):
        """Should create session for existing user."""
        _user = await user_factory(email="existing@testuser.dev")
        magic_link, token = await magic_link_factory(
            email="existing@testuser.dev",
        )

        response = await client.get(
            "/auth/magic",
            params={"token": token, "redirect": "/"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "session_id" in response.cookies

    async def test_verify_invalid_token(self, client: AsyncClient):
        """Should reject invalid token."""
        response = await client.get(
            "/auth/magic",
            params={"token": "invalid-token", "redirect": "/"},
        )

        assert response.status_code == 400
        assert "Invalid" in response.json()["detail"]

    async def test_verify_expired_token(self, client: AsyncClient, magic_link_factory):
        """Should reject expired token."""
        magic_link, token = await magic_link_factory(expired=True)

        response = await client.get(
            "/auth/magic",
            params={"token": token, "redirect": "/"},
        )

        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()

    async def test_verify_used_token(self, client: AsyncClient, magic_link_factory):
        """Should reject already-used token."""
        magic_link, token = await magic_link_factory(used=True)

        response = await client.get(
            "/auth/magic",
            params={"token": token, "redirect": "/"},
        )

        assert response.status_code == 400
        assert "already been used" in response.json()["detail"].lower()
