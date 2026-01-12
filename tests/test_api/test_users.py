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
        assert data["delivery_time_local"] == "08:00"
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


class TestUpdatePreferences:
    """Tests for PATCH /api/me/preferences."""

    async def test_update_timezone(
        self, client: AsyncClient, session_factory, user_factory, db_session
    ):
        """Should update user timezone."""
        user = await user_factory(timezone="Europe/Paris")
        session = await session_factory(user=user)

        response = await client.patch(
            "/api/me/preferences",
            json={"timezone": "America/New_York"},
            cookies={"session_id": str(session.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["timezone"] == "America/New_York"

    async def test_update_delivery_time(
        self, client: AsyncClient, session_factory, user_factory, db_session
    ):
        """Should update delivery time."""
        user = await user_factory(delivery_time="08:00")
        session = await session_factory(user=user)

        response = await client.patch(
            "/api/me/preferences",
            json={"delivery_time_local": "09:30"},
            cookies={"session_id": str(session.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["delivery_time_local"] == "09:30"

    async def test_update_both(
        self, client: AsyncClient, session_factory, user_factory, db_session
    ):
        """Should update both timezone and delivery time."""
        user = await user_factory()
        session = await session_factory(user=user)

        response = await client.patch(
            "/api/me/preferences",
            json={
                "timezone": "Asia/Tokyo",
                "delivery_time_local": "07:00",
            },
            cookies={"session_id": str(session.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["timezone"] == "Asia/Tokyo"
        assert data["delivery_time_local"] == "07:00"

    async def test_invalid_timezone_rejected(
        self, client: AsyncClient, session_factory, user_factory, db_session
    ):
        """Should reject invalid timezone."""
        user = await user_factory()
        session = await session_factory(user=user)

        response = await client.patch(
            "/api/me/preferences",
            json={"timezone": "Invalid/Timezone"},
            cookies={"session_id": str(session.id)},
        )

        assert response.status_code == 422  # Validation error

    async def test_invalid_delivery_time_rejected(
        self, client: AsyncClient, session_factory, user_factory, db_session
    ):
        """Should reject invalid delivery time format."""
        user = await user_factory()
        session = await session_factory(user=user)

        response = await client.patch(
            "/api/me/preferences",
            json={"delivery_time_local": "invalid"},
            cookies={"session_id": str(session.id)},
        )

        assert response.status_code == 422  # Validation error

    async def test_unauthenticated_rejected(self, client: AsyncClient):
        """Should reject unauthenticated requests."""
        response = await client.patch(
            "/api/me/preferences",
            json={"timezone": "America/New_York"},
        )

        assert response.status_code == 401


class TestGetTimezones:
    """Tests for GET /api/timezones."""

    async def test_returns_timezone_list(self, client: AsyncClient):
        """Should return list of common timezones."""
        response = await client.get("/api/timezones")

        assert response.status_code == 200
        data = response.json()
        assert "timezones" in data
        assert isinstance(data["timezones"], list)
        assert len(data["timezones"]) > 0
        assert "America/New_York" in data["timezones"]
        assert "Europe/Paris" in data["timezones"]
        assert "Asia/Tokyo" in data["timezones"]


class TestUnsubscribe:
    """Tests for POST /api/me/unsubscribe."""

    async def test_unsubscribe_success(
        self, client: AsyncClient, session_factory, user_factory, db_session
    ):
        """Should unsubscribe user from emails."""
        user = await user_factory()
        user.is_subscribed = True
        await db_session.flush()
        session = await session_factory(user=user)

        response = await client.post(
            "/api/me/unsubscribe",
            cookies={"session_id": str(session.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

        # Verify user is now unsubscribed
        await db_session.refresh(user)
        assert user.is_subscribed is False

    async def test_unsubscribe_unauthenticated(self, client: AsyncClient):
        """Should reject unauthenticated requests."""
        response = await client.post("/api/me/unsubscribe")
        assert response.status_code == 401


class TestResubscribe:
    """Tests for POST /api/me/resubscribe."""

    async def test_resubscribe_success(
        self, client: AsyncClient, session_factory, user_factory, db_session
    ):
        """Should resubscribe user to emails."""
        user = await user_factory()
        user.is_subscribed = False
        await db_session.flush()
        session = await session_factory(user=user)

        response = await client.post(
            "/api/me/resubscribe",
            cookies={"session_id": str(session.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

        # Verify user is now subscribed
        await db_session.refresh(user)
        assert user.is_subscribed is True

    async def test_resubscribe_unauthenticated(self, client: AsyncClient):
        """Should reject unauthenticated requests."""
        response = await client.post("/api/me/resubscribe")
        assert response.status_code == 401
