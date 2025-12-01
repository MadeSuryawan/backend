"""Tests for cache manager."""

from unittest.mock import Mock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.clients.memory_client import MemoryClient
from app.managers.cache_manager import CacheManager


@pytest.mark.asyncio
async def test_cache_manager_initialization(cache_manager: CacheManager) -> None:
    """Test cache manager initialization."""
    assert cache_manager is not None
    assert cache_manager._client is not None


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
    await cache_manager.set("key1", {"data": "value1"})
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
    await cache_manager.set("key1", {"data": "value1"})
    await cache_manager.set("key2", {"data": "value2"})

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
    await cache_manager.set("key1", {"data": "value1"})
    await cache_manager.set("key2", {"data": "value2"})
    await cache_manager.set("key3", {"data": "value3"})
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


@pytest.mark.asyncio
@patch(
    "app.clients.redis_client.RedisClient.connect",
    side_effect=RedisConnectionError("Test error"),
)
async def test_cache_manager_fallback_to_memory(
    mock_connect: Mock,  # noqa: ARG001
) -> None:
    """Test that CacheManager falls back to in-memory cache when Redis connection fails."""
    manager = CacheManager()
    await manager.initialize()

    assert not manager.is_redis_available
    assert isinstance(manager._client, MemoryClient)

    # Test a basic operation
    await manager.set("key", {"value": "test"}, namespace="fallback")
    result = await manager.get("key", namespace="fallback")
    assert result == {"value": "test"}

    await manager.shutdown()


@pytest.mark.asyncio
async def test_cache_health_check(cache_manager: CacheManager) -> None:
    """Test cache health check."""
    health = await cache_manager.health_check()

    assert "backend" in health
    assert "statistics" in health
    assert health["status"] == "healthy"


@pytest.mark.asyncio
async def test_get_or_set(cache_manager: CacheManager) -> None:
    """Test get_or_set with callback."""
    call_count = 0

    async def expensive_callback() -> dict[str, str]:
        nonlocal call_count
        call_count += 1
        return {"computed": "value"}

    # First call should execute callback
    result1 = await cache_manager.get_or_set(
        "computed_key",
        expensive_callback,
        ttl=600,
    )
    assert result1 == {"computed": "value"}
    assert call_count == 1

    # Second call should use cache
    result2 = await cache_manager.get_or_set(
        "computed_key",
        expensive_callback,
        ttl=600,
    )
    assert result2 == {"computed": "value"}
    assert call_count == 1  # Callback not called again


@pytest.mark.asyncio
async def test_get_or_set_force_refresh(cache_manager: CacheManager) -> None:
    """Test get_or_set with force_refresh."""
    call_count = 0

    async def callback() -> dict[str, int]:
        nonlocal call_count
        call_count += 1
        return {"count": call_count}

    # First call
    result1 = await cache_manager.get_or_set("refresh_key", callback, ttl=600)
    assert result1 == {"count": 1}

    # Force refresh should call callback again
    result2 = await cache_manager.get_or_set(
        "refresh_key",
        callback,
        ttl=600,
        force_refresh=True,
    )
    assert result2 == {"count": 2}


@pytest.mark.asyncio
async def test_build_key_without_namespace(cache_manager: CacheManager) -> None:
    """Test _build_key without namespace."""
    key = cache_manager._build_key("mykey")
    assert "mykey" in key
    assert cache_manager.cache_config.key_prefix in key


@pytest.mark.asyncio
async def test_build_key_with_namespace(cache_manager: CacheManager) -> None:
    """Test _build_key with namespace."""
    key = cache_manager._build_key("mykey", namespace="myns")
    assert "mykey" in key
    assert "myns" in key
    assert cache_manager.cache_config.key_prefix in key


@pytest.mark.asyncio
async def test_expire_key(cache_manager: CacheManager) -> None:
    """Test expire sets expiration on a key."""
    await cache_manager.set("expire_key", {"data": "test"}, ttl=3600)
    result = await cache_manager.expire("expire_key", 60)
    assert result is True
    ttl = await cache_manager.ttl("expire_key")
    assert ttl <= 60


@pytest.mark.asyncio
async def test_get_or_create_lock_lru_eviction(cache_manager: CacheManager) -> None:
    """Test that locks are evicted when MAX_LOCKS is exceeded."""
    original_max = CacheManager.MAX_LOCKS
    CacheManager.MAX_LOCKS = 3

    try:
        # Create 4 locks to trigger eviction
        cache_manager._get_or_create_lock("lock1")
        cache_manager._get_or_create_lock("lock2")
        cache_manager._get_or_create_lock("lock3")
        cache_manager._get_or_create_lock("lock4")

        # Should only have 3 locks due to LRU eviction
        assert len(cache_manager._locks) == 3
        assert "lock1" not in cache_manager._locks
    finally:
        CacheManager.MAX_LOCKS = original_max


@pytest.mark.asyncio
async def test_get_or_create_lock_moves_to_end(cache_manager: CacheManager) -> None:
    """Test that accessing existing lock moves it to end for LRU."""
    cache_manager._get_or_create_lock("lockA")
    cache_manager._get_or_create_lock("lockB")

    # Access lockA again - should move to end
    cache_manager._get_or_create_lock("lockA")

    keys = list(cache_manager._locks.keys())
    assert keys[-1] == "lockA"


@pytest.mark.asyncio
async def test_try_reconnect_redis_already_available(cache_manager: CacheManager) -> None:
    """Test _try_reconnect_redis when already connected."""
    cache_manager.is_redis_available = True
    result = await cache_manager._try_reconnect_redis()
    assert result is True


@pytest.mark.asyncio
@patch("app.clients.redis_client.RedisClient.connect")
async def test_try_reconnect_redis_success(
    mock_connect: Mock,
) -> None:
    """Test _try_reconnect_redis successful reconnection."""
    manager = CacheManager()
    manager.is_redis_available = False

    mock_connect.return_value = None  # Simulate successful connection

    result = await manager._try_reconnect_redis()
    assert result is True
    assert manager.is_redis_available is True


@pytest.mark.asyncio
@patch(
    "app.clients.redis_client.RedisClient.connect",
    side_effect=RedisConnectionError("Connection refused"),
)
async def test_try_reconnect_redis_failure(
    mock_connect: Mock,  # noqa: ARG001
) -> None:
    """Test _try_reconnect_redis failed reconnection."""
    manager = CacheManager()
    manager.is_redis_available = False

    result = await manager._try_reconnect_redis()
    assert result is False
    assert manager.is_redis_available is False


@pytest.mark.asyncio
async def test_fallback_to_memory(cache_manager: CacheManager) -> None:
    """Test _fallback_to_memory switches to memory client."""
    cache_manager.is_redis_available = True
    await cache_manager._fallback_to_memory()

    assert cache_manager.is_redis_available is False
    assert isinstance(cache_manager._client, MemoryClient)


@pytest.mark.asyncio
async def test_disable_redis_when_already_disabled(cache_manager: CacheManager) -> None:
    """Test disable_redis when Redis is already disabled."""
    cache_manager.is_redis_available = False
    cache_manager._client = cache_manager.memory_client

    result = await cache_manager.disable_redis()

    assert result.status == "unchanged"
    assert result.backend == "in-memory"
    assert "already disabled" in result.message


@pytest.mark.asyncio
async def test_disable_redis_success(cache_manager: CacheManager) -> None:
    """Test disable_redis successfully disables Redis."""
    # Setup: pretend Redis is available
    cache_manager.is_redis_available = True
    cache_manager._client = cache_manager.redis_client

    result = await cache_manager.disable_redis()

    assert result.status == "success"
    assert result.backend == "in-memory"
    assert cache_manager.is_redis_available is False
    assert isinstance(cache_manager._client, MemoryClient)


@pytest.mark.asyncio
async def test_enable_redis_when_already_enabled(cache_manager: CacheManager) -> None:
    """Test enable_redis when Redis is already enabled."""
    cache_manager.is_redis_available = True

    result = await cache_manager.enable_redis()

    assert result.status == "unchanged"
    assert result.backend == "redis"
    assert "already enabled" in result.message


@pytest.mark.asyncio
@patch("app.clients.redis_client.RedisClient.connect")
async def test_enable_redis_success(mock_connect: Mock) -> None:
    """Test enable_redis successfully enables Redis."""
    mock_connect.return_value = None  # Simulate successful connection

    manager = CacheManager()
    manager.is_redis_available = False
    manager._client = manager.memory_client

    result = await manager.enable_redis()

    assert result.status == "success"
    assert result.backend == "redis"
    assert manager.is_redis_available is True
    mock_connect.assert_called_once()


@pytest.mark.asyncio
@patch(
    "app.clients.redis_client.RedisClient.connect",
    side_effect=RedisConnectionError("Connection refused"),
)
async def test_enable_redis_failure(mock_connect: Mock) -> None:  # noqa: ARG001
    """Test enable_redis when Redis connection fails."""
    manager = CacheManager()
    manager.is_redis_available = False
    manager._client = manager.memory_client

    result = await manager.enable_redis()

    assert result.status == "error"
    assert result.backend == "in-memory"
    assert "Failed to connect" in result.message
    assert manager.is_redis_available is False


@pytest.mark.asyncio
async def test_disable_and_enable_redis_round_trip(cache_manager: CacheManager) -> None:
    """Test disabling and then enabling Redis works correctly."""
    # First, set some data while using current backend
    await cache_manager.set("test_key", {"data": "value"})

    # Disable Redis
    disable_result = await cache_manager.disable_redis()
    assert disable_result.backend == "in-memory"
    assert cache_manager.is_redis_available is False

    # Cache operations should still work with in-memory backend
    await cache_manager.set("memory_key", {"memory": "data"})
    value = await cache_manager.get("memory_key")
    assert value == {"memory": "data"}
