"""Fixtures for managers tests."""

from collections.abc import AsyncGenerator, Generator
from unittest.mock import AsyncMock

import pytest

from app.main import app


async def mock_scan_iter(*args, **kwargs) -> AsyncGenerator[str, None]:
    """Mock async generator for scan_iter."""
    yield "limits:test:1"
    yield "limits:test:2"


@pytest.fixture(autouse=True)
def setup_cache_manager() -> Generator[None, None, None]:
    """Set up cache_manager on app state for limiter tests."""
    mock_cache_manager = AsyncMock()
    mock_cache_manager.is_redis_available = True
    mock_cache_manager.redis_client = AsyncMock()
    mock_cache_manager.redis_client.ping = AsyncMock(return_value=True)
    # Set up scan_iter as an async generator
    mock_cache_manager.redis_client.scan_iter = mock_scan_iter
    app.state.cache_manager = mock_cache_manager
    yield
    # Clean up after test
    if hasattr(app.state, "cache_manager"):
        delattr(app.state, "cache_manager")
