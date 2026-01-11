"""Tests for event endpoints."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestCreateEvent:
    """Tests for POST /api/events."""

    async def test_create_event_anonymous(self, client: AsyncClient):
        """Should create event for anonymous user."""
        response = await client.post(
            "/api/events",
            json={
                "event_name": "issue_view",
                "properties": {"issue_date": "2026-01-10"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["event_id"] is not None
        assert data["ts"] is not None

    async def test_create_event_authenticated(
        self, client: AsyncClient, session_factory, user_factory, db_session
    ):
        """Should associate event with authenticated user."""
        user = await user_factory()
        session = await session_factory(user=user)

        response = await client.post(
            "/api/events",
            json={
                "event_name": "subscribe_click",
                "properties": {"source": "header"},
            },
            cookies={"session_id": str(session.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    async def test_create_event_empty_properties(self, client: AsyncClient):
        """Should allow events without properties."""
        response = await client.post(
            "/api/events",
            json={"event_name": "page_view"},
        )

        assert response.status_code == 200

    async def test_create_event_missing_name(self, client: AsyncClient):
        """Should reject events without event_name."""
        response = await client.post(
            "/api/events",
            json={"properties": {}},
        )

        assert response.status_code == 422

    async def test_create_event_long_name(self, client: AsyncClient):
        """Should reject event names exceeding max length."""
        response = await client.post(
            "/api/events",
            json={"event_name": "a" * 150},  # max is 100
        )

        assert response.status_code == 422
