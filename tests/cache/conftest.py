# tests/cache/conftest.py
"""Pytest configuration and fixtures for cache tests."""

from collections.abc import AsyncGenerator

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.clients.memory_client import MemoryClient
from app.db.database import engine
from app.dependencies import get_cache_manager
from app.main import app
from app.managers.cache_manager import CacheManager
from app.managers.rate_limiter import limiter


@pytest.fixture
async def cache_manager() -> AsyncGenerator[CacheManager]:
    """
    Create cache manager for testing.

    Automatically initializes, clears cache, resets statistics,
    and cleans up on teardown.
    """
    manager = CacheManager()
    await manager.initialize()
    await manager.clear()  # Clear cache before each test
    manager.reset_statistics()  # Reset statistics before each test

    yield manager

    await manager.shutdown()


@pytest.fixture
async def client(cache_manager: CacheManager) -> AsyncGenerator[AsyncClient]:
    """
    Create async HTTP client for testing FastAPI endpoints.

    Automatically disables rate limiting and overrides the cache dependency
    to use the test-scoped cache_manager fixture.
    """

    limiter.enabled = False

    # Dispose any existing database connections to prevent event loop issues
    # This is necessary because the engine is a global singleton and may be
    # tied to a different event loop from a previous test
    await engine.dispose()

    # --- DEPENDENCY INJECTION OVERRIDE ---
    # This forces the app to use our test 'cache_manager' instance
    # instead of the global one defined in app/managers/__init__.py
    app.dependency_overrides[get_cache_manager] = lambda: cache_manager

    async with (
        LifespanManager(app),
        AsyncClient(
            base_url="http://test",
            transport=ASGITransport(app=app),
        ) as ac,
    ):
        yield ac

    # Clean up overrides after test
    app.dependency_overrides = {}


@pytest.fixture
def memory_client() -> MemoryClient:
    """
    Create an in-memory cache client for testing.

    Use this fixture for testing cache operations without Redis dependency.
    """
    return MemoryClient()
