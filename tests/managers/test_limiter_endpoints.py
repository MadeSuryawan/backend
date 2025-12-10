from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_limiter_status_endpoint() -> None:
    """Test getting limiter status."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Patch RedisClient class methods directly
        with patch(
            "app.clients.redis_client.RedisClient.ping",
            new_callable=AsyncMock,
        ) as mock_ping:
            mock_ping.return_value = True

            response = await client.get("/limiter/status")

            assert response.status_code == 200
            data = response.json()
            assert data["healthy"] is True
            assert data["storage"] == "redis"


@pytest.mark.asyncio
async def test_limiter_reset_admin_only_success() -> None:
    """Test calling reset from localhost succeeds."""
    # By default AsyncClient uses 127.0.0.1 as client host
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with (
            patch("app.clients.redis_client.RedisClient.ping", new_callable=AsyncMock) as mock_ping,
            patch("app.clients.redis_client.RedisClient.scan_iter") as mock_scan,
            patch(
                "app.clients.redis_client.RedisClient.delete",
                new_callable=AsyncMock,
            ) as mock_delete,
        ):
            mock_ping.return_value = True

            # Mock scan_iter to yield some keys
            async def scan_gen(pattern: str) -> AsyncGenerator[str]:
                yield "limits:test:1"
                yield "limits:test:2"

            mock_scan.side_effect = scan_gen

            mock_delete.return_value = 1

            # Call with all_endpoints=True
            response = await client.post(
                "/limiter/reset",
                json={"all_endpoints": True, "key": "test_key"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 2
            assert "Reset 2 rate limit keys" in data["message"]


@pytest.mark.asyncio
async def test_limiter_reset_forbidden_remote() -> None:
    """Test calling reset from remote IP is forbidden."""
    # We need to simulate a request from a non-localhost IP.
    # We can do this by creating a client with a custom transport or patching Request.client
    # Easier to patch the endpoint logic's check or the request object properties, but let's try patching the request object via middleware or directly if possible.
    # Actually, AsyncClient allows setting client=... in transport?

    # Let's mock the value in the endpoint: request.client.host
    # Since we can't easily mock Request inside the endpoint without complex patching,
    # we can trust that FastAPI sets request.client based on connection.
    # However, with TestClient/AsyncClient, it's usually fixed.

    # We will assume safely that we need to pass headers or configure client?
    # Wait, Starlette TestClient sets client host. httpx AsyncClient with ASGITransport defaults to 127.0.0.1.

    # Let's inject a middleware or patch the Request.
    # Actually, simpler: patch the check in the router itself? No, that defeats the purpose.

    # We can use `client` kwarg in ASGITransport in recent versions, or `scope`.
    transport = ASGITransport(app=app, client=("10.0.0.1", 1234))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/limiter/reset", json={"all_endpoints": True})
        assert response.status_code == 403
        assert response.json()["detail"] == "Admin access required (localhost only)"


@pytest.mark.asyncio
async def test_limiter_reset_requires_all_endpoints() -> None:
    """Test failure when all_endpoints is False."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/limiter/reset", json={"all_endpoints": False})
        assert response.status_code == 501
