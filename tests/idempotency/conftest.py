# tests/idempotency/conftest.py
"""Fixtures for idempotency tests."""

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.managers.idempotency_manager import IdempotencyManager
from app.schemas.idempotency import IdempotencyRecord, IdempotencyStatus


class MockCacheClient:
    """Mock cache client for testing."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._data[key] = value

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                deleted += 1
        return deleted

    async def scan_iter(self, pattern: str) -> AsyncIterator[str]:
        """Mock scan_iter that yields matching keys."""
        import fnmatch

        # Convert Redis pattern to fnmatch pattern
        fnmatch_pattern = pattern.replace("*", "*")
        for key in list(self._data.keys()):
            if fnmatch.fnmatch(key, fnmatch_pattern):
                yield key


@pytest.fixture
def mock_cache() -> MockCacheClient:
    """Create a mock cache client."""
    return MockCacheClient()


@pytest.fixture
def idempotency_manager(mock_cache: MockCacheClient) -> IdempotencyManager:
    """Create an idempotency manager with mock cache."""
    return IdempotencyManager(
        cache_client=mock_cache,  # type: ignore[arg-type]
        prefix="test_idempotency",
        ttl=3600,
    )


@pytest.fixture
def sample_idempotency_key() -> str:
    """Return a sample idempotency key."""
    return "550e8400-e29b-41d4-a716-446655440000"


@pytest.fixture
def sample_response() -> dict[str, Any]:
    """Return a sample response for testing."""
    return {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "username": "johndoe",
        "email": "johndoe@example.com",
    }
