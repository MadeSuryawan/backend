"""Focused cache route coverage without app lifespan startup."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.dependencies import get_cache_manager
from app.dependencies.dependencies import is_admin
from app.main import app
from app.models import UserDB
from app.schemas import CacheToggleResponse


def make_cache_stats() -> dict[str, int | str]:
    return {
        "hits": 5,
        "misses": 2,
        "sets": 3,
        "deletes": 1,
        "evictions": 0,
        "errors": 0,
        "total_bytes_written": 100,
        "total_bytes_read": 50,
        "hit_rate": "71.43%",
        "total_requests": 7,
        "created_at": "2026-03-11T00:00:00Z",
        "last_updated_at": "2026-03-11T00:00:00Z",
    }


@pytest.fixture(autouse=True)
def clear_cache_route_overrides() -> Generator:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def cache_route_manager() -> MagicMock:
    manager = MagicMock()
    manager.get_statistics.return_value = make_cache_stats()
    manager.ping = AsyncMock(return_value=True)
    manager.clear = AsyncMock()
    manager.disable_redis = AsyncMock(
        return_value=CacheToggleResponse(
            status="success",
            message="Redis disabled",
            backend="in-memory",
        ),
    )
    manager.enable_redis = AsyncMock(
        return_value=CacheToggleResponse(
            status="success",
            message="Redis enabled",
            backend="redis",
        ),
    )
    return manager


def override_cache_route_dependencies(manager: MagicMock, admin_user: UserDB) -> None:
    async def admin_override() -> UserDB:
        return admin_user

    app.dependency_overrides[get_cache_manager] = lambda: manager
    app.dependency_overrides[is_admin] = admin_override


@pytest.mark.asyncio
async def test_get_cache_stats_returns_manager_statistics(
    client: AsyncClient,
    admin_user: UserDB,
    cache_route_manager: MagicMock,
) -> None:
    override_cache_route_dependencies(cache_route_manager, admin_user)

    response = await client.get("/cache/stats")

    assert response.status_code == 200
    assert response.json() == {"status": "success", "data": make_cache_stats()}
    cache_route_manager.get_statistics.assert_called_once_with()


@pytest.mark.asyncio
async def test_ping_cache_returns_success_when_manager_is_alive(
    client: AsyncClient,
    admin_user: UserDB,
    cache_route_manager: MagicMock,
) -> None:
    override_cache_route_dependencies(cache_route_manager, admin_user)

    response = await client.get("/cache/ping")

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "message": "Cache server is reachable",
        "error_code": None,
    }
    cache_route_manager.ping.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_ping_cache_returns_503_when_manager_is_unreachable(
    client: AsyncClient,
    admin_user: UserDB,
    cache_route_manager: MagicMock,
) -> None:
    cache_route_manager.ping = AsyncMock(return_value=False)
    override_cache_route_dependencies(cache_route_manager, admin_user)

    response = await client.get("/cache/ping")

    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "message": "Cache server is not reachable",
        "error_code": 503,
    }
    cache_route_manager.ping.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_reset_stats_resets_manager_statistics(
    client: AsyncClient,
    admin_user: UserDB,
    cache_route_manager: MagicMock,
) -> None:
    override_cache_route_dependencies(cache_route_manager, admin_user)

    response = await client.get("/cache/reset-stats")

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "message": "Cache statistics reset",
        "error_code": None,
    }
    cache_route_manager.reset_statistics.assert_called_once_with()


@pytest.mark.asyncio
async def test_clear_cache_clears_manager_entries(
    client: AsyncClient,
    admin_user: UserDB,
    cache_route_manager: MagicMock,
) -> None:
    override_cache_route_dependencies(cache_route_manager, admin_user)

    response = await client.delete("/cache/clear")

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "message": "Cache cleared successfully",
        "error_code": None,
    }
    cache_route_manager.clear.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_disable_redis_returns_toggle_response(
    client: AsyncClient,
    admin_user: UserDB,
    cache_route_manager: MagicMock,
) -> None:
    override_cache_route_dependencies(cache_route_manager, admin_user)

    response = await client.post("/cache/redis/disable")

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "message": "Redis disabled",
        "backend": "in-memory",
        "error_code": None,
    }
    cache_route_manager.disable_redis.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_enable_redis_returns_toggle_response(
    client: AsyncClient,
    admin_user: UserDB,
    cache_route_manager: MagicMock,
) -> None:
    override_cache_route_dependencies(cache_route_manager, admin_user)

    response = await client.post("/cache/redis/enable")

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "message": "Redis enabled",
        "backend": "redis",
        "error_code": None,
    }
    cache_route_manager.enable_redis.assert_awaited_once_with()
