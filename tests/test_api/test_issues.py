"""Tests for issue endpoints."""

from datetime import date

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestGetIssue:
    """Tests for GET /api/issues/{date}."""

    async def test_get_issue_not_found(self, client: AsyncClient):
        """Should return 404 for non-existent issue."""
        response = await client.get("/api/issues/2020-01-01")

        assert response.status_code == 404
        assert "No issue found" in response.json()["detail"]

    async def test_get_issue_public_view(self, client: AsyncClient, issue_factory, db_session):
        """Should return full content for public view (no soft wall)."""
        issue_date = date(2026, 1, 10)
        await issue_factory(issue_date=issue_date, num_clusters=10)

        response = await client.get(f"/api/issues/{issue_date}")

        assert response.status_code == 200
        data = response.json()
        assert data["date"] == str(issue_date)
        assert len(data["items"]) == 10

        # All items should be fully visible (soft wall removed)
        for item in data["items"]:
            assert item["locked"] is False
            assert "takeaway" in item
            assert "bullets" in item

    async def test_get_issue_full_view_unauthenticated(
        self, client: AsyncClient, issue_factory, db_session
    ):
        """Should return full content even when unauthenticated (no soft wall)."""
        issue_date = date(2026, 1, 11)
        await issue_factory(issue_date=issue_date, num_clusters=10)

        response = await client.get(
            f"/api/issues/{issue_date}",
            params={"view": "full"},
        )

        assert response.status_code == 200
        data = response.json()

        # All items should be fully visible (soft wall removed)
        for item in data["items"]:
            assert item["locked"] is False
            assert "takeaway" in item
            assert "bullets" in item

    async def test_get_issue_full_view_authenticated(
        self,
        client: AsyncClient,
        issue_factory,
        session_factory,
        user_factory,
        db_session,
    ):
        """Should return full content for authenticated users."""
        issue_date = date(2026, 1, 12)
        await issue_factory(issue_date=issue_date, num_clusters=10)

        user = await user_factory()
        session = await session_factory(user=user)

        response = await client.get(
            f"/api/issues/{issue_date}",
            params={"view": "full"},
            cookies={"session_id": str(session.id)},
        )

        assert response.status_code == 200
        data = response.json()

        # All items should be fully visible
        for item in data["items"]:
            assert item["locked"] is False
            assert "takeaway" in item
            assert "bullets" in item
            assert "citations" in item

    async def test_get_issue_invalid_date_format(self, client: AsyncClient):
        """Should reject invalid date formats."""
        response = await client.get("/api/issues/invalid-date")

        assert response.status_code == 422

    async def test_get_issue_invalid_view_param(
        self, client: AsyncClient, issue_factory, db_session
    ):
        """Should reject invalid view parameter."""
        issue_date = date(2026, 1, 13)
        await issue_factory(issue_date=issue_date)

        response = await client.get(
            f"/api/issues/{issue_date}",
            params={"view": "invalid"},
        )

        assert response.status_code == 422
