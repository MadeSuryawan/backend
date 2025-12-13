"""Tests for the in-memory cache client."""

import asyncio

import pytest

from app.clients.memory_client import MemoryClient


@pytest.mark.asyncio
async def test_set_and_get(memory_client: MemoryClient) -> None:
    """Test setting and getting a value."""
    await memory_client.set("key", "value")
    result = await memory_client.get("key")
    assert result == "value"


@pytest.mark.asyncio
async def test_get_non_existent(memory_client: MemoryClient) -> None:
    """Test getting a non-existent value."""
    result = await memory_client.get("non_existent_key")
    assert result is None


@pytest.mark.asyncio
async def test_delete(memory_client: MemoryClient) -> None:
    """Test deleting a value."""
    await memory_client.set("key", "value")
    await memory_client.delete("key")
    result = await memory_client.get("key")
    assert result is None


@pytest.mark.asyncio
async def test_exists(memory_client: MemoryClient) -> None:
    """Test checking if a key exists."""
    await memory_client.set("key", "value")
    exists = await memory_client.exists("key")
    assert exists == 1
    non_exists = await memory_client.exists("non_existent_key")
    assert non_exists == 0


@pytest.mark.asyncio
async def test_flush_all(memory_client: MemoryClient) -> None:
    """Test flushing the entire cache."""
    await memory_client.set("key1", "value1")
    await memory_client.set("key2", "value2")
    await memory_client.flush_all()
    assert await memory_client.exists("key1") == 0
    assert await memory_client.exists("key2") == 0


@pytest.mark.asyncio
async def test_ttl_and_expiration(memory_client: MemoryClient) -> None:
    """Test TTL and expiration of a key."""
    await memory_client.set("key", "value", ex=1)
    assert await memory_client.get("key") == "value"
    await asyncio.sleep(1.1)
    assert await memory_client.get("key") is None


@pytest.mark.asyncio
async def test_ttl_value(memory_client: MemoryClient) -> None:
    """Test the TTL value of a key."""
    await memory_client.set("key", "value", ex=10)
    ttl = await memory_client.ttl("key")
    assert 8 < ttl <= 10


@pytest.mark.asyncio
async def test_expire(memory_client: MemoryClient) -> None:
    """Test setting expiration on a key."""
    await memory_client.set("key", "value")
    await memory_client.expire("key", 1)
    assert await memory_client.get("key") == "value"
    await asyncio.sleep(1.1)
    assert await memory_client.get("key") is None


@pytest.mark.asyncio
async def test_info(memory_client: MemoryClient) -> None:
    """Test getting info from the cache."""
    info = await memory_client.info()
    assert info["server"] == "In-Memory Cache"
    assert "used_memory_human" in info
    assert "total_keys" in info
    assert "max_entries" in info


@pytest.mark.asyncio
async def test_scan_iter(memory_client: MemoryClient) -> None:
    """Test scanning keys with pattern matching."""
    await memory_client.set("prefix:key1", "value1")
    await memory_client.set("prefix:key2", "value2")
    await memory_client.set("other:key3", "value3")

    keys = [key async for key in memory_client.scan_iter("prefix:*")]
    assert len(keys) == 2
    assert "prefix:key1" in keys
    assert "prefix:key2" in keys


@pytest.mark.asyncio
async def test_memory_limits() -> None:
    """Test that memory limits trigger LRU eviction."""
    # Create a client with very low limits
    limited_client = MemoryClient(max_entries=3)

    await limited_client.set("key1", "value1")
    await limited_client.set("key2", "value2")
    await limited_client.set("key3", "value3")

    # This should trigger eviction of key1 (oldest)
    await limited_client.set("key4", "value4")

    # key1 should be evicted
    assert await limited_client.get("key1") is None
    # key4 should exist
    assert await limited_client.get("key4") == "value4"


@pytest.mark.asyncio
async def test_lru_ordering() -> None:
    """Test that LRU ordering is maintained on access."""
    limited_client = MemoryClient(max_entries=3)

    await limited_client.set("key1", "value1")
    await limited_client.set("key2", "value2")
    await limited_client.set("key3", "value3")

    # Access key1 to make it recently used
    await limited_client.get("key1")

    # Add key4 - should evict key2 (now oldest)
    await limited_client.set("key4", "value4")

    # key1 should still exist (was accessed)
    assert await limited_client.get("key1") == "value1"
    # key2 should be evicted
    assert await limited_client.get("key2") is None


@pytest.mark.asyncio
async def test_ping(memory_client: MemoryClient) -> None:
    """Test ping returns True when connected."""
    assert await memory_client.ping() is True


@pytest.mark.asyncio
async def test_ttl_non_existent_key(memory_client: MemoryClient) -> None:
    """Test TTL returns -2 for non-existent key."""
    ttl = await memory_client.ttl("non_existent")
    assert ttl == -2


@pytest.mark.asyncio
async def test_ttl_no_expiration(memory_client: MemoryClient) -> None:
    """Test TTL returns -1 for key without expiration."""
    await memory_client.set("permanent_key", "value")
    ttl = await memory_client.ttl("permanent_key")
    assert ttl == -1


@pytest.mark.asyncio
async def test_expire_non_existent_key(memory_client: MemoryClient) -> None:
    """Test expire returns False for non-existent key."""
    result = await memory_client.expire("non_existent", 60)
    assert result is False


@pytest.mark.asyncio
async def test_delete_multiple_keys(memory_client: MemoryClient) -> None:
    """Test deleting multiple keys at once."""
    await memory_client.set("key1", "value1")
    await memory_client.set("key2", "value2")
    await memory_client.set("key3", "value3")

    count = await memory_client.delete("key1", "key2", "key_not_exist")
    assert count == 2
    assert await memory_client.get("key3") == "value3"


@pytest.mark.asyncio
async def test_exists_multiple_keys(memory_client: MemoryClient) -> None:
    """Test exists with multiple keys."""
    await memory_client.set("key1", "value1")
    await memory_client.set("key2", "value2")

    count = await memory_client.exists("key1", "key2", "key3")
    assert count == 2


@pytest.mark.asyncio
async def test_set_updates_existing_key(memory_client: MemoryClient) -> None:
    """Test that set updates existing key value."""
    await memory_client.set("key", "value1")
    await memory_client.set("key", "value2")
    result = await memory_client.get("key")
    assert result == "value2"


@pytest.mark.asyncio
async def test_set_removes_ttl_on_update(memory_client: MemoryClient) -> None:
    """Test that set without TTL removes existing TTL."""
    await memory_client.set("key", "value1", ex=60)
    await memory_client.set("key", "value2")  # No TTL
    ttl = await memory_client.ttl("key")
    assert ttl == -1


@pytest.mark.asyncio
async def test_close_stops_cleanup_task(memory_client: MemoryClient) -> None:
    """Test that close properly stops the cleanup task."""
    await memory_client.close()
    assert memory_client.is_connected is False
    assert memory_client._cleanup_task is None


@pytest.mark.asyncio
async def test_scan_iter_no_matches(memory_client: MemoryClient) -> None:
    """Test scan_iter returns empty when no matches."""
    await memory_client.set("key1", "value1")
    keys = [key async for key in memory_client.scan_iter("nonexistent:*")]
    assert len(keys) == 0


@pytest.mark.asyncio
async def test_is_expired_false_for_no_ttl() -> None:
    """Test _is_expired returns False for keys without TTL."""
    client = MemoryClient()
    client._cache["key"] = "value"
    assert client._is_expired("key") is False


@pytest.mark.asyncio
async def test_estimate_entry_size() -> None:
    """Test _estimate_entry_size calculates size."""
    client = MemoryClient()
    size = client._estimate_entry_size("key", "value")
    assert size > 0
