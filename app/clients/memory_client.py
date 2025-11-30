"""In-memory cache client for fallback when Redis is not available."""

from logging import getLogger
from time import time
from typing import Any

from app.configs import file_logger
from app.utils import today_str

logger = file_logger(getLogger(__name__))


class MemoryClient:
    """
    A simple asynchronous in-memory cache client that mimics RedisClient.

    This class provides a basic in-memory key-value store with support for
    time-to-live (TTL) expiration. It is designed to be a drop-in
    replacement for the RedisClient when Redis is unavailable.
    """

    def __init__(self) -> None:
        """Initialize the MemoryClient."""
        self._cache: dict[str, Any] = {}
        self._ttl: dict[str, float] = {}
        self.is_connected: bool = True

    def _is_expired(self, key: str) -> bool:
        """
        Check if a key has expired.

        Args:
            key: The key to check.

        Returns:
            True if the key has expired, False otherwise.
        """
        if key in self._ttl:
            return time() > self._ttl[key]
        return False

    async def get(self, key: str) -> str | None:
        """
        Get a value from the cache.

        Args:
            key: The key of the item to retrieve.

        Returns:
            The value if it exists and has not expired, otherwise None.
        """
        if self._is_expired(key):
            logger.debug(f"key {key} is expired")
            await self.delete(key)
            return None
        return self._cache.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        """
        Set a value in the cache with an optional TTL.

        Args:
            key: The key of the item to set.
            value: The value to store.
            ex: The expiration time in seconds.

        Returns:
            True if the value was set successfully.
        """
        self._cache[key] = value
        if ex:
            self._ttl[key] = time() + ex
        return True

    async def delete(self, *keys: str) -> int:
        """
        Delete one or more keys from the cache.

        Args:
            keys: The keys to delete.

        Returns:
            The number of keys that were deleted.
        """
        logger.debug(f"{keys=}")
        count = 0
        for key in keys:
            if key in self._cache:
                del self._cache[key]
                if key in self._ttl:
                    del self._ttl[key]
                count += 1
        return count

    async def exists(self, *keys: str) -> int:
        """
        Check if one or more keys exist in the cache.

        Args:
            keys: The keys to check.

        Returns:
            The number of keys that exist.
        """
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
        return True

    async def info(self) -> dict[str, str]:
        """Get information about the in-memory cache."""
        return {
            "server": "In-Memory Cache",
            "connected_clients": "1",
            "uptime_in_seconds": "N/A",
            "total_system_memory": "N/A",
            "used_memory_human": f"{len(self._cache)} keys",
            "last_save_time": today_str(),
        }

    async def ttl(self, key: str) -> int:
        """
        Get the remaining time to live of a key.

        Args:
            key: The key to check.

        Returns:
            The remaining TTL in seconds, -1 if it has no expiry,
            or -2 if the key does not exist or has expired.
        """
        if self._is_expired(key):
            await self.delete(key)
            return -2

        if key not in self._cache:
            return -2

        if key not in self._ttl:
            return -1

        return int(self._ttl[key] - time())

    async def expire(self, key: str, seconds: int) -> bool:
        """
        Set an expiration time on a key.

        Args:
            key: The key to set the expiration on.
            seconds: The TTL in seconds.

        Returns:
            True if the expiration was set, False otherwise.
        """
        if key in self._cache:
            self._ttl[key] = time() + seconds
            return True
        return False

    async def close(self) -> None:
        """Close the client (no-op for in-memory)."""
        self.is_connected = False
