"""Pytest configuration and fixtures for cache tests."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from app.clients import MemoryClient
from app.main import app
from app.managers.cache_manager import CacheManager
from app.managers.cache_manager import cache_manager as global_cache_manager
from app.managers.rate_limiter import limiter


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """
    Create async HTTP client for testing FastAPI endpoints.

    Automatically disables rate limiting and manages cache lifecycle.
    """
    limiter.enabled = False
    await global_cache_manager.initialize()
    async with AsyncClient(
        base_url="http://test",
        transport=ASGITransport(app=app),
    ) as ac:
        yield ac
    await global_cache_manager.shutdown()


@pytest.fixture
async def cache_manager() -> AsyncGenerator[CacheManager]:
    """
    Create cache manager for testing.

    Automatically initializes, clears cache, resets statistics,
    and cleans up on teardown.
    """
    manager = CacheManager()
    try:
        await manager.initialize()
        await manager.clear()  # Clear cache before each test
        manager.reset_statistics()  # Reset statistics before each test
        yield manager
    finally:
        await manager.shutdown()


@pytest.fixture
def memory_client() -> MemoryClient:
    """
    Create an in-memory cache client for testing.

    Use this fixture for testing cache operations without Redis dependency.
    """
    return MemoryClient()
