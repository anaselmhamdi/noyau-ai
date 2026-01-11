"""Tests for health check endpoint."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestHealthCheck:
    """Tests for GET /health."""

    async def test_health_check(self, client: AsyncClient):
        """Should return healthy status."""
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
