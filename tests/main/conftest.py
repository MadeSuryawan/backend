# tests/main/conftest.py
"""Pytest configuration and fixtures for main tests."""

from collections.abc import AsyncGenerator

from httpx import ASGITransport, AsyncClient
from pytest import fixture

from app.main import app
from app.managers.rate_limiter import limiter


@fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """Create async HTTP client for testing FastAPI endpoints."""
    limiter.enabled = True
    async with AsyncClient(
        base_url="http://test",
        transport=ASGITransport(app=app),
    ) as ac:
        app.state.limiter = limiter
        yield ac
