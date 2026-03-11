# tests/main/conftest.py
"""Pytest configuration and fixtures for main tests."""

from collections.abc import AsyncGenerator
from uuid import uuid4

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from pytest import fixture

from app.dependencies.dependencies import is_admin
from app.main import app
from app.managers.rate_limiter import limiter
from app.models import UserDB


@fixture
def admin_user() -> UserDB:
    """Create an admin user for main endpoint tests."""
    return UserDB(
        uuid=uuid4(),
        username="admin",
        email="admin@test.com",
        password_hash="hash",
        is_verified=True,
        role="admin",
    )


@fixture
async def client(admin_user: UserDB) -> AsyncGenerator[AsyncClient]:
    """Create authenticated admin HTTP client for testing main endpoints."""
    limiter.enabled = True

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
        app.state.limiter = limiter
        yield ac

    app.dependency_overrides = {}


@fixture
async def unauthenticated_client() -> AsyncGenerator[AsyncClient]:
    """Create unauthenticated HTTP client for access control tests."""
    limiter.enabled = True

    async with (
        LifespanManager(app),
        AsyncClient(
            base_url="http://test",
            transport=ASGITransport(app=app),
        ) as ac,
    ):
        app.state.limiter = limiter
        yield ac
