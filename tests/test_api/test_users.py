"""Tests for user endpoints."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestGetMe:
    """Tests for GET /api/me."""

    async def test_me_unauthenticated(self, client: AsyncClient):
        """Should return authed=false when not logged in."""
        response = await client.get("/api/me")

        assert response.status_code == 200
        data = response.json()
        assert data["authed"] is False
        assert data["email"] is None

    async def test_me_authenticated(
        self, client: AsyncClient, session_factory, user_factory, db_session
    ):
        """Should return user info when authenticated."""
        user = await user_factory(email="authed@example.com")
        session = await session_factory(user=user)

        response = await client.get(
            "/api/me",
            cookies={"session_id": str(session.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["authed"] is True
        assert data["email"] == "authed@example.com"
        assert data["timezone"] == "Europe/Paris"
        assert data["ref_code"] is not None

    async def test_me_invalid_session(self, client: AsyncClient):
        """Should return authed=false for invalid session."""
        response = await client.get(
            "/api/me",
            cookies={"session_id": "invalid-session-id"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["authed"] is False

    async def test_me_expired_session(
        self, client: AsyncClient, session_factory, user_factory, db_session
    ):
        """Should return authed=false for expired session."""
        from datetime import timedelta

        from app.core.datetime_utils import utc_now

        user = await user_factory()
        session = await session_factory(user=user)

        # Manually expire the session
        session.expires_at = utc_now() - timedelta(days=1)
        await db_session.flush()

        response = await client.get(
            "/api/me",
            cookies={"session_id": str(session.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["authed"] is False
