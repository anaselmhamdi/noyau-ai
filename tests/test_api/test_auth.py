"""Tests for authentication endpoints."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestRequestMagicLink:
    """Tests for POST /auth/request-link."""

    async def test_request_link_success(self, client: AsyncClient):
        """Should return ok when requesting magic link."""
        response = await client.post(
            "/auth/request-link",
            json={"email": "test@example.com", "redirect": "/daily/2026-01-10"},
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
            json={"email": "test@example.com"},
        )

        assert response.status_code == 200


class TestVerifyMagicLink:
    """Tests for GET /auth/magic."""

    async def test_verify_valid_token_new_user(
        self, client: AsyncClient, magic_link_factory, db_session
    ):
        """Should create user and session for valid token."""
        magic_link, token = await magic_link_factory(
            email="new@example.com",
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
        _user = await user_factory(email="existing@example.com")
        magic_link, token = await magic_link_factory(
            email="existing@example.com",
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
