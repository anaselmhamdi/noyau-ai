"""Tests for rate limiting on auth endpoints."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestRateLimiting:
    """Tests for rate limiting on /auth/request-link."""

    async def test_rate_limit_allows_normal_usage(self, client: AsyncClient):
        """Should allow requests within rate limit."""
        # Make 3 requests (well under 5/minute limit)
        for i in range(3):
            response = await client.post(
                "/auth/request-link",
                json={"email": f"user{i}@gmail.com"},
            )
            assert response.status_code == 200

    async def test_rate_limit_blocks_excessive_requests(self, client: AsyncClient):
        """Should block requests exceeding rate limit."""
        # Make 6 requests quickly (exceeds 5/minute limit)
        responses = []
        for i in range(6):
            response = await client.post(
                "/auth/request-link",
                json={"email": f"user{i}@gmail.com"},
            )
            responses.append(response.status_code)

        # First 5 should succeed, 6th should be rate limited
        assert responses[:5] == [200, 200, 200, 200, 200]
        assert responses[5] == 429

    async def test_rate_limit_error_message(self, client: AsyncClient):
        """Should return appropriate error message when rate limited."""
        # Exhaust rate limit
        for i in range(5):
            await client.post(
                "/auth/request-link",
                json={"email": f"user{i}@gmail.com"},
            )

        # 6th request should be rate limited
        response = await client.post(
            "/auth/request-link",
            json={"email": "user6@gmail.com"},
        )

        assert response.status_code == 429
        data = response.json()
        assert "too many requests" in data["detail"].lower()

    async def test_rate_limit_does_not_affect_magic_verification(
        self, client: AsyncClient, magic_link_factory
    ):
        """Rate limiting on request-link should not affect magic link verification."""
        # Create a valid magic link
        magic_link, token = await magic_link_factory(email="test@testuser.dev")

        # Exhaust rate limit on request-link
        for i in range(5):
            await client.post(
                "/auth/request-link",
                json={"email": f"user{i}@gmail.com"},
            )

        # Magic link verification should still work (different endpoint)
        response = await client.get(
            "/auth/magic",
            params={"token": token, "redirect": "/"},
            follow_redirects=False,
        )

        assert response.status_code == 302  # Should redirect, not 429
