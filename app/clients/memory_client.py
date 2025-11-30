"""In-memory cache client for fallback when Redis is not available."""

from asyncio import CancelledError, Task, create_task
from asyncio import sleep as asyncio_sleep
from contextlib import suppress
from logging import getLogger
from time import time
from typing import Any

from app.configs import file_logger
from app.utils import today_str

logger = file_logger(getLogger(__name__))


class MemoryClient:
    """
    A simple asynchronous in-memory cache client that mimics RedisClient.

    Includes Active Expiration to prevent memory leaks.
    """

    def __init__(self) -> None:
        """Initialize the MemoryClient."""
        self._cache: dict[str, Any] = {}
        self._ttl: dict[str, float] = {}
        self.is_connected: bool = True
        self._cleanup_task: Task | None = None
        self._cleanup_interval: int = 60  # seconds

    async def start_lifecycle(self) -> None:
        """Start background maintenance tasks."""
        if not self._cleanup_task:
            self.is_connected = True
            self._cleanup_task = create_task(self._cleanup_loop())
            logger.info("MemoryClient active expiration task started.")

    async def _cleanup_loop(self) -> None:
        """Background loop to remove expired keys."""
        while self.is_connected:
            try:
                await asyncio_sleep(self._cleanup_interval)
                await self._active_expire()
            except CancelledError:
                break
            except Exception:
                logger.exception("Error in memory cleanup loop")

    async def _active_expire(self) -> None:
        """Scan and remove expired keys."""
        if not self._ttl:
            return

        keys_to_delete = [key for key in self._ttl if self._is_expired(key)]
        if keys_to_delete:
            count = await self.delete(*keys_to_delete)
            logger.debug(f"Memory cleanup: removed {count} expired keys.")

    def _is_expired(self, key: str) -> bool:
        """Check if a key has expired."""
        if key in self._ttl:
            return time() > self._ttl[key]
        return False

    async def get(self, key: str) -> str | None:
        """Get a value from the cache."""
        if self._is_expired(key):
            await self.delete(key)
            return None
        return self._cache.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        """Set a value in the cache with an optional TTL."""
        self._cache[key] = value
        if ex:
            self._ttl[key] = time() + ex
        elif key in self._ttl:
            # If no new TTL is provided but key exists, remove old TTL (Standard Redis behavior)
            # OR keep it? Redis SET removes TTL unless KEEPTTL is used.
            # We will assume new SET wipes old TTL.
            del self._ttl[key]
        return True

    async def delete(self, *keys: str) -> int:
        """Delete one or more keys from the cache."""
        count = 0
        for key in keys:
            if key in self._cache:
                del self._cache[key]
                if key in self._ttl:
                    del self._ttl[key]
                count += 1
        return count

    async def exists(self, *keys: str) -> int:
        """Check if one or more keys exist in the cache."""
        count = 0
        for key in keys:
            if key in self._cache and not self._is_expired(key):
                count += 1
        return count

    async def flush_all(self) -> bool:
        """Clear the entire cache."""
        self._cache.clear()
        self._ttl.clear()
        return True

    async def ping(self) -> bool:
        """Check if the cache is alive."""
        return self.is_connected

    async def info(self) -> dict[str, str]:
        """Get information about the in-memory cache."""
        return {
            "server": "In-Memory Cache",
            "connected_clients": "1",
            "used_memory_human": f"{len(self._cache)} keys",
            "last_save_time": today_str(),
        }

    async def ttl(self, key: str) -> int:
        """Get the remaining time to live of a key."""
        if self._is_expired(key):
            await self.delete(key)
            return -2

        if key not in self._cache:
            return -2

        if key not in self._ttl:
            return -1

        return int(self._ttl[key] - time())

    async def expire(self, key: str, seconds: int) -> bool:
        """Set an expiration time on a key."""
        if key in self._cache:
            self._ttl[key] = time() + seconds
            return True
        return False

    async def close(self) -> None:
        """Stop the client and cleanup tasks."""
        self.is_connected = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            with suppress(CancelledError):
                await self._cleanup_task
            self._cleanup_task = None
