"""In-memory cache client for fallback when Redis is not available."""

from asyncio import CancelledError, Lock, Task, create_task
from asyncio import sleep as asyncio_sleep
from collections import OrderedDict
from collections.abc import AsyncGenerator
from contextlib import suppress
from fnmatch import fnmatch
from logging import DEBUG, getLogger
from sys import getsizeof
from time import time

from app.configs import file_logger

logger = file_logger(getLogger(__name__))


class MemoryClient:
    """
    A thread-safe asynchronous in-memory cache client that mimics RedisClient.

    Features:
        - Active expiration via background cleanup task
        - Memory limits with LRU eviction
        - Entry count limits
        - Thread-safe operations via asyncio.Lock
        - Pattern-based key scanning
    """

    # Default limits - can be overridden via constructor
    DEFAULT_MAX_ENTRIES: int = 100_000
    DEFAULT_MAX_MEMORY_MB: int = 100
    DEFAULT_CLEANUP_INTERVAL: int = 60  # seconds
    DEFAULT_CLEANUP_BATCH_SIZE: int = 1000

    def __init__(
        self,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        max_memory_mb: int = DEFAULT_MAX_MEMORY_MB,
        cleanup_interval: int = DEFAULT_CLEANUP_INTERVAL,
    ) -> None:
        """
        Initialize the MemoryClient with configurable limits.

        Args:
            max_entries: Maximum number of cache entries before LRU eviction.
            max_memory_mb: Maximum memory usage in megabytes before eviction.
            cleanup_interval: Interval in seconds for background cleanup.
        """
        # Use OrderedDict for LRU eviction support
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._ttl: dict[str, float] = {}
        self.is_connected: bool = True
        self._cleanup_task: Task[None] | None = None

        # Configuration
        self._max_entries = max_entries
        self._max_memory_bytes = max_memory_mb * 1024 * 1024
        self._cleanup_interval = cleanup_interval
        self._cleanup_batch_size = self.DEFAULT_CLEANUP_BATCH_SIZE

        # Memory tracking
        self._current_memory: int = 0

        # Thread safety lock
        self._lock = Lock()

    async def start_lifecycle(self) -> None:
        """Start background maintenance tasks."""
        async with self._lock:
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
        """Scan and remove expired keys in batches for better performance."""
        async with self._lock:
            if not self._ttl:
                return

            # Process in batches to avoid blocking
            keys = list(self._ttl.keys())
            expired_keys: list[str] = []

            for i in range(0, len(keys), self._cleanup_batch_size):
                batch = keys[i : i + self._cleanup_batch_size]
                expired_keys.extend(k for k in batch if self._is_expired_internal(k))

            if expired_keys:
                count = self._delete_internal(*expired_keys)
                if logger.isEnabledFor(DEBUG):
                    logger.debug("Memory cleanup: removed %d expired keys.", count)

    def _is_expired_internal(self, key: str) -> bool:
        """Check if a key has expired (internal, no lock)."""
        if key in self._ttl:
            return time() > self._ttl[key]
        return False

    def _is_expired(self, key: str) -> bool:
        """Check if a key has expired (public method)."""
        return self._is_expired_internal(key)

    def _estimate_entry_size(self, key: str, value: str) -> int:
        """Estimate memory size of a cache entry."""
        return getsizeof(key) + getsizeof(value)

    def _evict_oldest(self) -> None:
        """Evict the oldest entry (LRU policy) - internal, no lock."""
        if self._cache:
            key, value = self._cache.popitem(last=False)
            self._current_memory -= self._estimate_entry_size(key, value)
            if key in self._ttl:
                del self._ttl[key]

    def _delete_internal(self, *keys: str) -> int:
        """Delete keys without acquiring lock (internal use only)."""
        count = 0
        for key in keys:
            if key in self._cache:
                value = self._cache.pop(key)
                self._current_memory -= self._estimate_entry_size(key, value)
                if key in self._ttl:
                    del self._ttl[key]
                count += 1
        return count

    async def get(self, key: str) -> str | None:
        """Get a value from the cache."""
        async with self._lock:
            if self._is_expired_internal(key):
                self._delete_internal(key)
                return None
            value = self._cache.get(key)
            if value is not None:
                # Move to end for LRU tracking
                self._cache.move_to_end(key)
            return value

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        """Set a value in the cache with optional TTL and automatic eviction."""
        async with self._lock:
            entry_size = self._estimate_entry_size(key, value)

            # If key already exists, subtract old size
            if key in self._cache:
                old_value = self._cache[key]
                self._current_memory -= self._estimate_entry_size(key, old_value)

            # Evict entries if we exceed limits
            while (
                len(self._cache) >= self._max_entries
                and key not in self._cache
                or self._current_memory + entry_size > self._max_memory_bytes
            ) and self._cache:
                self._evict_oldest()

            # Store the value
            self._cache[key] = value
            self._cache.move_to_end(key)  # Mark as recently used
            self._current_memory += entry_size

            if ex:
                self._ttl[key] = time() + ex
            elif key in self._ttl:
                # Redis SET removes TTL unless KEEPTTL is used
                del self._ttl[key]

            return True

    async def delete(self, *keys: str) -> int:
        """Delete one or more keys from the cache."""
        async with self._lock:
            return self._delete_internal(*keys)

    async def exists(self, *keys: str) -> int:
        """Check if one or more keys exist in the cache."""
        async with self._lock:
            count = 0
            for key in keys:
                if key in self._cache and not self._is_expired_internal(key):
                    count += 1
            return count

    async def flush_all(self) -> bool:
        """Clear the entire cache."""
        async with self._lock:
            self._cache.clear()
            self._ttl.clear()
            self._current_memory = 0
            return True

    async def ping(self) -> bool:
        """Check if the cache is alive."""
        return self.is_connected

    async def info(self) -> dict[str, str | int]:
        """Get information about the in-memory cache."""
        async with self._lock:
            return {
                "server": "In-Memory Cache",
                "connected_clients": 1,
                "used_memory_bytes": self._current_memory,
                "used_memory_human": f"{self._current_memory / 1024 / 1024:.2f}MB",
                "total_keys": len(self._cache),
                "max_entries": self._max_entries,
                "max_memory_mb": self._max_memory_bytes // 1024 // 1024,
            }

    async def ttl(self, key: str) -> int:
        """Get the remaining time to live of a key."""
        async with self._lock:
            if self._is_expired_internal(key):
                self._delete_internal(key)
                return -2

            if key not in self._cache:
                return -2

            if key not in self._ttl:
                return -1

            return int(self._ttl[key] - time())

    async def expire(self, key: str, seconds: int) -> bool:
        """Set an expiration time on a key."""
        async with self._lock:
            if key in self._cache:
                self._ttl[key] = time() + seconds
                return True
            return False

    async def scan_iter(
        self,
        pattern: str,
        count: int = 100,  # noqa: ARG002 - kept for API compatibility with RedisClient
    ) -> AsyncGenerator[str]:
        """
        Yield keys matching the pattern.

        Uses fnmatch for pattern matching (supports wildcards like * and ?).

        Args:
            pattern: Glob-style pattern to match keys.
            count: Batch size hint (ignored for in-memory, kept for API compatibility).

        Yields:
            Keys matching the pattern.
        """
        async with self._lock:
            # Create a copy of keys to avoid modification during iteration
            keys = list(self._cache.keys())

        for key in keys:
            if fnmatch(key, pattern):
                yield key

    async def close(self) -> None:
        """Stop the client and cleanup tasks."""
        async with self._lock:
            self.is_connected = False
            if self._cleanup_task:
                self._cleanup_task.cancel()
                with suppress(CancelledError):
                    await self._cleanup_task
                self._cleanup_task = None
