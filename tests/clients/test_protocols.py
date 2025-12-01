"""Tests for app/clients/protocols.py."""

from logging import DEBUG, INFO
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.clients.protocols import CacheClientProtocol, is_debug_enabled


class TestIsDebugEnabled:
    """Tests for is_debug_enabled function."""

    def test_debug_enabled_when_level_is_debug(self) -> None:
        """Test returns True when logger level is DEBUG."""
        assert is_debug_enabled(DEBUG) is True

    def test_debug_enabled_when_level_is_below_debug(self) -> None:
        """Test returns True when logger level is below DEBUG (e.g., NOTSET=0)."""
        assert is_debug_enabled(0) is True

    def test_debug_disabled_when_level_is_info(self) -> None:
        """Test returns False when logger level is INFO."""
        assert is_debug_enabled(INFO) is False

    def test_debug_disabled_when_level_is_warning(self) -> None:
        """Test returns False when logger level is WARNING (30)."""
        assert is_debug_enabled(30) is False

    def test_debug_disabled_when_level_is_error(self) -> None:
        """Test returns False when logger level is ERROR (40)."""
        assert is_debug_enabled(40) is False


class MockCacheClient:
    """A mock implementation of CacheClientProtocol for testing."""

    def __init__(self) -> None:
        self.store: dict[str, tuple[str, int | None]] = {}

    async def get(self, key: str) -> str | None:
        """Get a value from the cache."""
        if key in self.store:
            return self.store[key][0]
        return None

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        """Set a value in the cache."""
        self.store[key] = (value, ex)
        return True

    async def delete(self, *keys: str) -> int:
        """Delete keys from the cache."""
        count = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                count += 1
        return count

    async def exists(self, *keys: str) -> int:
        """Check if keys exist."""
        return sum(1 for key in keys if key in self.store)

    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration on a key."""
        if key in self.store:
            value = self.store[key][0]
            self.store[key] = (value, seconds)
            return True
        return False

    async def ttl(self, key: str) -> int:
        """Get TTL of a key."""
        if key in self.store:
            exp = self.store[key][1]
            return exp if exp is not None else -1
        return -2

    async def ping(self) -> bool:
        """Ping the cache."""
        return True

    async def info(self) -> dict[str, Any]:
        """Get cache info."""
        return {"keys": len(self.store), "type": "mock"}

    async def flush_all(self) -> bool:
        """Clear all entries."""
        self.store.clear()
        return True


class TestCacheClientProtocol:
    """Tests for CacheClientProtocol runtime checking."""

    def test_mock_client_is_instance_of_protocol(self) -> None:
        """Test that MockCacheClient is recognized as implementing the protocol."""
        client = MockCacheClient()
        assert isinstance(client, CacheClientProtocol)

    def test_non_conforming_class_is_not_instance(self) -> None:
        """Test that a non-conforming class is not an instance."""

        class NotAClient:
            pass

        assert not isinstance(NotAClient(), CacheClientProtocol)

    def test_partial_implementation_is_not_instance(self) -> None:
        """Test that partial implementation is not recognized."""

        class PartialClient:
            async def get(self, key: str) -> str | None:
                return None

        # Only has get() but missing other methods
        assert not isinstance(PartialClient(), CacheClientProtocol)

    @pytest.mark.asyncio
    async def test_mock_client_get_set_operations(self) -> None:
        """Test get and set operations on mock client."""
        client = MockCacheClient()

        # Initially empty
        result = await client.get("key1")
        assert result is None

        # Set value
        await client.set("key1", "value1", ex=60)
        result = await client.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_mock_client_delete_operation(self) -> None:
        """Test delete operation on mock client."""
        client = MockCacheClient()
        await client.set("key1", "value1")
        await client.set("key2", "value2")

        deleted = await client.delete("key1", "key2", "key3")
        assert deleted == 2

    @pytest.mark.asyncio
    async def test_mock_client_exists_operation(self) -> None:
        """Test exists operation on mock client."""
        client = MockCacheClient()
        await client.set("key1", "value1")

        count = await client.exists("key1", "key2")
        assert count == 1

    @pytest.mark.asyncio
    async def test_mock_client_flush_all(self) -> None:
        """Test flush_all operation on mock client."""
        client = MockCacheClient()
        await client.set("key1", "value1")
        await client.set("key2", "value2")

        result = await client.flush_all()
        assert result is True
        assert await client.exists("key1") == 0
