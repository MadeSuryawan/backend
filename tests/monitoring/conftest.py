"""Test fixtures for monitoring tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from fastapi import FastAPI


@pytest.fixture
def test_app() -> FastAPI:
    """Create a test FastAPI application with monitoring configured."""
    from fastapi import FastAPI

    from app.monitoring import setup_monitoring

    app = FastAPI(title="Test App", version="1.0.0")
    setup_monitoring(app, enable_tracing=False)

    return app


@pytest.fixture
async def client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as ac:
        yield ac
