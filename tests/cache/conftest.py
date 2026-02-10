# tests/cache/conftest.py
"""Pytest configuration and fixtures for cache tests."""

from collections.abc import AsyncGenerator
from datetime import timedelta
from uuid import uuid4

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.clients.memory_client import MemoryClient
from app.db.database import engine
from app.dependencies import get_cache_manager
from app.dependencies.dependencies import is_admin
from app.main import app
from app.managers.cache_manager import CacheManager
from app.managers.rate_limiter import limiter
from app.managers.token_manager import create_access_token
from app.models import UserDB


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
def admin_user() -> UserDB:
    """Create an admin user for testing."""
    return UserDB(
        uuid=uuid4(),
        username="admin",
        email="admin@test.com",
        password_hash="hash",
        is_active=True,
        is_verified=True,
        role="admin",
    )


@pytest.fixture
def admin_token(admin_user: UserDB) -> str:
    """Create an access token for the admin user."""
    return create_access_token(
        user_id=admin_user.uuid,
        username=admin_user.username,
        expires_delta=timedelta(minutes=30),
    )


@pytest.fixture
async def client(
    cache_manager: CacheManager,
    admin_user: UserDB,
) -> AsyncGenerator[AsyncClient]:
    """
    Create async HTTP client for testing FastAPI endpoints.

    Automatically disables rate limiting and overrides the cache dependency
    to use the test-scoped cache_manager fixture. Also mocks the admin user
    authentication.
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

    # Mock the is_admin to return admin user for authentication
    async def mock_is_admin() -> UserDB:
        return admin_user

    app.dependency_overrides[is_admin] = mock_is_admin

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
