"""Tests for the in-memory cache client."""

import asyncio

import pytest

from app.clients import MemoryClient


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
    assert "keys" in info["used_memory_human"]
