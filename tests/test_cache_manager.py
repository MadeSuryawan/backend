"""Tests for cache manager."""

from collections.abc import AsyncGenerator

import pytest

from app.managers.cache_manager import CacheManager


@pytest.fixture
async def cache_manager() -> AsyncGenerator[CacheManager]:
    """Create cache manager for testing."""
    manager = CacheManager()
    try:
        await manager.initialize()
        yield manager
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_cache_manager_initialization(cache_manager: CacheManager) -> None:
    """Test cache manager initialization."""
    assert cache_manager is not None
    assert cache_manager.redis_client is not None


@pytest.mark.asyncio
async def test_cache_set_and_get(cache_manager: CacheManager) -> None:
    """Test cache set and get operations."""
    test_key = "test_key"
    test_value = {"name": "test", "value": 123}

    # Set value
    result = await cache_manager.set(test_key, test_value, ttl=600)
    assert result is True

    # Get value
    cached_value = await cache_manager.get(test_key)
    assert cached_value == test_value


@pytest.mark.asyncio
async def test_cache_delete(cache_manager: CacheManager) -> None:
    """Test cache delete operation."""
    test_key = "test_key_delete"
    test_value = {"data": "test"}

    # Set and delete
    await cache_manager.set(test_key, test_value)
    deleted = await cache_manager.delete(test_key)
    assert deleted == 1

    # Verify deletion
    cached_value = await cache_manager.get(test_key)
    assert cached_value is None


@pytest.mark.asyncio
async def test_cache_exists(cache_manager: CacheManager) -> None:
    """Test cache exists operation."""
    test_key = "test_key_exists"
    test_value = {"data": "test"}

    # Check non-existent key
    exists = await cache_manager.exists(test_key)
    assert exists == 0

    # Set and check
    await cache_manager.set(test_key, test_value)
    exists = await cache_manager.exists(test_key)
    assert exists == 1


@pytest.mark.asyncio
async def test_cache_with_namespace(cache_manager: CacheManager) -> None:
    """Test cache with namespace."""
    key = "test_key"
    namespace = "test_namespace"
    value = {"data": "test"}

    # Set with namespace
    await cache_manager.set(key, value, namespace=namespace)

    # Get with namespace
    cached_value = await cache_manager.get(key, namespace=namespace)
    assert cached_value == value

    # Verify different namespace
    cached_value = await cache_manager.get(key, namespace="other_namespace")
    assert cached_value is None


@pytest.mark.asyncio
async def test_cache_ttl(cache_manager: CacheManager) -> None:
    """Test cache TTL operations."""
    test_key = "test_key_ttl"
    test_value = {"data": "test"}

    # Set with TTL
    await cache_manager.set(test_key, test_value, ttl=100)

    # Check TTL
    ttl = await cache_manager.ttl(test_key)
    assert ttl > 0
    assert ttl <= 100


@pytest.mark.asyncio
async def test_cache_statistics(cache_manager: CacheManager) -> None:
    """Test cache statistics."""
    # Reset statistics
    cache_manager.reset_statistics()

    # Perform operations
    await cache_manager.set("key1", "value1")
    await cache_manager.get("key1")  # Hit
    await cache_manager.get("key2")  # Miss

    # Check statistics
    stats = cache_manager.get_statistics()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["sets"] == 1


@pytest.mark.asyncio
async def test_cache_ping(cache_manager: CacheManager) -> None:
    """Test cache ping."""
    is_alive = await cache_manager.ping()
    assert is_alive is True


@pytest.mark.asyncio
async def test_cache_clear(cache_manager: CacheManager) -> None:
    """Test cache clear operation."""
    # Set multiple values
    await cache_manager.set("key1", "value1")
    await cache_manager.set("key2", "value2")

    # Clear cache
    await cache_manager.clear()

    # Verify cleared
    value1 = await cache_manager.get("key1")
    value2 = await cache_manager.get("key2")
    assert value1 is None
    assert value2 is None


@pytest.mark.asyncio
async def test_cache_clear_with_statistics_reset(cache_manager: CacheManager) -> None:
    """Test cache clear operation with statistics reset."""
    # Reset statistics
    cache_manager.reset_statistics()

    # Set multiple values and perform operations
    await cache_manager.set("key1", "value1")
    await cache_manager.set("key2", "value2")
    await cache_manager.set("key3", "value3")
    await cache_manager.get("key1")  # Hit
    await cache_manager.get("key4")  # Miss

    # Check statistics before clear
    stats_before = cache_manager.get_statistics()
    assert stats_before["sets"] == 3
    assert stats_before["hits"] == 1
    assert stats_before["misses"] == 1

    # Clear cache (which also resets statistics)
    await cache_manager.clear()

    # Verify all values are cleared
    value1 = await cache_manager.get("key1")
    value2 = await cache_manager.get("key2")
    value3 = await cache_manager.get("key3")
    assert value1 is None
    assert value2 is None
    assert value3 is None

    # Check statistics after clear (should be reset and count 3 misses from the get calls)
    stats_after = cache_manager.get_statistics()
    assert stats_after["hits"] == 0
    assert stats_after["misses"] == 3  # Three get calls after clear all miss
    assert stats_after["sets"] == 0
