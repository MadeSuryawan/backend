from collections.abc import AsyncGenerator
from datetime import timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.managers.token_manager import create_access_token
from app.models import UserDB


@pytest.mark.asyncio
async def test_limiter_status_endpoint() -> None:
    """Test getting limiter status with admin authentication."""
    # Create admin user and token
    admin_user = UserDB(
        uuid=uuid4(),
        username="admin",
        email="admin@test.com",
        password_hash="hash",
        is_verified=True,
        role="admin",
    )
    admin_token = create_access_token(
        user_id=admin_user.uuid,
        username=admin_user.username,
        expires_delta=timedelta(minutes=30),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Patch RedisClient class methods directly
        with (
            patch(
                "app.clients.redis_client.RedisClient.ping",
                new_callable=AsyncMock,
            ) as mock_ping,
            patch(
                "app.repositories.user.UserRepository.get_by_id",
                new_callable=AsyncMock,
            ) as mock_get_user,
        ):
            mock_ping.return_value = True
            mock_get_user.return_value = admin_user

            response = await client.get(
                "/limiter/status",
                headers={"Authorization": f"Bearer {admin_token}"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["healthy"] is True
            assert data["storage"] == "redis"


@pytest.mark.asyncio
async def test_limiter_status_forbidden_for_non_admin() -> None:
    """Test that limiter status endpoint requires admin authentication."""
    # Create regular user (not admin)
    regular_user = UserDB(
        uuid=uuid4(),
        username="user",
        email="user@test.com",
        password_hash="hash",
        is_verified=True,
        role="user",
    )
    user_token = create_access_token(
        user_id=regular_user.uuid,
        username=regular_user.username,
        expires_delta=timedelta(minutes=30),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch(
            "app.repositories.user.UserRepository.get_by_id",
            new_callable=AsyncMock,
        ) as mock_get_user:
            mock_get_user.return_value = regular_user

            response = await client.get(
                "/limiter/status",
                headers={"Authorization": f"Bearer {user_token}"},
            )
            assert response.status_code == 403
            assert "admin users only" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_limiter_status_unauthorized_without_token() -> None:
    """Test that limiter status endpoint returns 401 without authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/limiter/status")
        assert response.status_code == 401
        assert "Not authenticated" in response.json()["detail"]


@pytest.mark.asyncio
async def test_limiter_reset_admin_only_success() -> None:
    """Test calling reset with admin authentication succeeds."""
    # Create admin user and token
    admin_user = UserDB(
        uuid=uuid4(),
        username="admin",
        email="admin@test.com",
        password_hash="hash",
        is_verified=True,
        role="admin",
    )
    admin_token = create_access_token(
        user_id=admin_user.uuid,
        username=admin_user.username,
        expires_delta=timedelta(minutes=30),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with (
            patch("app.clients.redis_client.RedisClient.ping", new_callable=AsyncMock) as mock_ping,
            patch("app.clients.redis_client.RedisClient.scan_iter") as mock_scan,
            patch(
                "app.clients.redis_client.RedisClient.delete",
                new_callable=AsyncMock,
            ) as mock_delete,
            patch(
                "app.repositories.user.UserRepository.get_by_id",
                new_callable=AsyncMock,
            ) as mock_get_user,
        ):
            mock_ping.return_value = True
            mock_get_user.return_value = admin_user

            # Mock scan_iter to yield some keys
            async def scan_gen(pattern: str) -> AsyncGenerator[str]:
                yield "limits:test:1"
                yield "limits:test:2"

            mock_scan.side_effect = scan_gen

            mock_delete.return_value = 1

            # Call with all_endpoints=True and admin token
            response = await client.post(
                "/limiter/reset",
                json={"all_endpoints": True, "key": "test_key"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 2
            assert "Reset 2 rate limit keys" in data["message"]


@pytest.mark.asyncio
async def test_limiter_reset_forbidden_remote() -> None:
    """Test calling reset without admin authentication is forbidden."""
    # Create regular user (not admin)
    regular_user = UserDB(
        uuid=uuid4(),
        username="user",
        email="user@test.com",
        password_hash="hash",
        is_verified=True,
        role="user",
    )
    user_token = create_access_token(
        user_id=regular_user.uuid,
        username=regular_user.username,
        expires_delta=timedelta(minutes=30),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch(
            "app.repositories.user.UserRepository.get_by_id",
            new_callable=AsyncMock,
        ) as mock_get_user:
            mock_get_user.return_value = regular_user

            response = await client.post(
                "/limiter/reset",
                json={"all_endpoints": True},
                headers={"Authorization": f"Bearer {user_token}"},
            )
            assert response.status_code == 403
            assert "admin users only" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_limiter_reset_requires_all_endpoints() -> None:
    """Test failure when all_endpoints is False."""
    # Create admin user and token
    admin_user = UserDB(
        uuid=uuid4(),
        username="admin",
        email="admin@test.com",
        password_hash="hash",
        is_verified=True,
        role="admin",
    )
    admin_token = create_access_token(
        user_id=admin_user.uuid,
        username=admin_user.username,
        expires_delta=timedelta(minutes=30),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with (
            patch("app.clients.redis_client.RedisClient.ping", new_callable=AsyncMock) as mock_ping,
            patch(
                "app.repositories.user.UserRepository.get_by_id",
                new_callable=AsyncMock,
            ) as mock_get_user,
        ):
            mock_ping.return_value = True
            mock_get_user.return_value = admin_user

            response = await client.post(
                "/limiter/reset",
                json={"all_endpoints": False},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert response.status_code == 501
