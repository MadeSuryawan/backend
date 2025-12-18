# app/managers/cache_manager.py
"""Main cache manager for Redis caching operations with circuit breaker support."""

from asyncio import Lock as AsyncLock
from collections import OrderedDict
from collections.abc import Callable, Coroutine
from logging import DEBUG, getLogger
from threading import Lock as ThreadLock
from typing import Any

from pydantic_core import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError
from starlette import status

from app.clients.memory_client import MemoryClient
from app.clients.protocols import CacheClientProtocol
from app.clients.redis_client import RedisClient
from app.configs import CacheConfig, settings
from app.data import CacheStatistics
from app.errors import BASE_EXCEPTION, CacheDeserializationError, CacheKeyError
from app.schemas import CacheToggleResponse
from app.schemas.cache import CacheStatisticsData
from app.utils.cache_serializer import (
    compress,
    decompress,
    deserialize,
    do_compress,
    serialize,
)
from app.utils.helpers import file_logger

logger = file_logger(getLogger(__name__))


CacheCallback = Callable[..., Coroutine[Any, Any, Any]]


class CacheManager:
    """
    Main cache manager for Redis operations with advanced features.

    Features:
        - Request coalescing (Thundering Herd protection)
        - Automatic fallback to in-memory cache
        - Circuit breaker for Redis failures
        - LRU-based lock eviction to prevent memory leaks
        - Compression for large values
        - Statistics tracking
    """

    # Maximum number of locks to keep in memory (LRU eviction)
    MAX_LOCKS: int = 10_000

    def __init__(self) -> None:
        """Initialize cache manager."""
        self.redis_client = RedisClient()
        self.memory_client = MemoryClient()
        self._client: CacheClientProtocol = self.redis_client
        self.is_redis_available = False
        self.cache_config = CacheConfig()
        self.statistics = CacheStatistics()

        # Locks for request coalescing (Thundering Herd protection)
        # Using OrderedDict for LRU eviction
        self._locks: OrderedDict[str, AsyncLock] = OrderedDict()
        # Thread lock to protect the locks dictionary
        self._locks_lock = ThreadLock()

    async def initialize(self) -> None:
        """
        Initialize cache manager by connecting to Redis.

        If the Redis connection fails, it falls back to an in-memory cache.
        """
        try:
            if settings.REDIS_ENABLED:
                await self.redis_client.connect()
                self._client = self.redis_client
                self.is_redis_available = True
                return
            logger.info("Redis disabled. Using in-memory cache.")
            self._client = self.memory_client
            self.is_redis_available = False
            # Also start memory client in case we need to fallback later
            await self.memory_client.start_lifecycle()
        except RedisConnectionError as e:
            logger.warning(f"Redis connection failed: {e}. Falling back to in-memory cache.")
            self._client = self.memory_client
            self.is_redis_available = False
            await self.memory_client.start_lifecycle()
        logger.info("Cache manager initialized successfully.")

    async def shutdown(self) -> None:
        """Shutdown cache manager by closing the client connection."""
        if isinstance(self._client, RedisClient):
            await self._client.disconnect()
        # Ensure memory client is also closed properly
        await self.memory_client.close()
        logger.info("Cache manager shutdown successfully.")

    def _build_key(self, key: str, namespace: str | None = None) -> str:
        """Build full cache key with prefix and namespace."""
        prefix = self.cache_config.key_prefix
        return f"{prefix}:{namespace}:{key}" if namespace else f"{prefix}:{key}"

    async def get(
        self,
        key: str,
        namespace: str | None = None,
    ) -> object | None:
        """Get value from cache."""
        try:
            full_key = self._build_key(key, namespace)
            if logger.isEnabledFor(DEBUG):
                logger.debug("Getting from cache: %s", full_key)
            cached_value = await self._client.get(full_key)

            if cached_value is None:
                self.statistics.record_miss()
                return None

            self.statistics.record_hit()
            read_bytes = len(cached_value.encode("utf-8")) if isinstance(cached_value, str) else 0
            self.statistics.record_read(read_bytes)

            # Decompress if needed
            if isinstance(cached_value, str):
                cached_value = decompress(cached_value)

            # Deserialize
            return deserialize(cached_value)
        except BASE_EXCEPTION + (ValidationError, CacheDeserializationError) as e:
            logger.exception("Cache get failed for key: %s", key)
            self.statistics.record_error()
            mssg = f"Cache get failed for key {key}, {e}"
            raise CacheKeyError(mssg) from e

    async def set(
        self,
        key: str,
        value: object,
        ttl: int | None = None,
        namespace: str | None = None,
    ) -> bool:
        """Set value in cache."""
        try:
            full_key = self._build_key(key, namespace)
            serialized = serialize(value)

            # Determine compression
            if self.cache_config.compression_enabled and do_compress(
                serialized,
                self.cache_config.compression_threshold,
            ):
                serialized = compress(serialized)

            # Set expiration
            ex = ttl if ttl is not None else self.cache_config.default_ttl
            ex = min(ex, self.cache_config.max_ttl)

            success = await self._client.set(full_key, serialized, ex=ex)
            self.statistics.record_set(len(serialized.encode("utf-8")))
        except (RedisConnectionError,) + BASE_EXCEPTION as e:
            logger.exception("Cache set failed for key %s", key)
            self.statistics.record_error()
            mssg = f"Cache set failed for key {key}"
            raise CacheKeyError(mssg) from e
        return success

    async def delete(self, *keys: str, namespace: str | None = None) -> int:
        """Delete keys from cache."""
        try:
            full_keys = [self._build_key(key, namespace) for key in keys]
            deleted_count = await self._client.delete(*full_keys)
            if deleted_count:
                self.statistics.record_delete()
        except BASE_EXCEPTION as e:
            logger.exception("Cache delete failed for keys: %s", keys)
            self.statistics.record_error()
            mssg = "Cache delete failed"
            raise CacheKeyError(mssg) from e
        return deleted_count

    async def exists(self, *keys: str, namespace: str | None = None) -> int:
        """Check if keys exist."""
        try:
            full_keys = [self._build_key(key, namespace) for key in keys]
            return await self._client.exists(*full_keys)
        except BASE_EXCEPTION as e:
            logger.exception("Cache exists check failed for keys: %s", keys)
            self.statistics.record_error()
            mssg = "Cache exists check failed"
            raise CacheKeyError(mssg) from e

    def _get_or_create_lock(self, key: str) -> AsyncLock:
        """
        Get or create a lock for a key in a thread-safe manner.

        Uses LRU eviction to prevent memory leaks from unbounded lock growth.
        """
        with self._locks_lock:
            if key in self._locks:
                # Move to end for LRU tracking
                self._locks.move_to_end(key)
                return self._locks[key]

            # Evict oldest locks if we exceed the limit
            while len(self._locks) >= self.MAX_LOCKS:
                self._locks.popitem(last=False)

            # Create new lock
            lock = AsyncLock()
            self._locks[key] = lock
            return lock

    async def get_or_set(
        self,
        key: str,
        callback: CacheCallback,
        ttl: int | None = None,
        namespace: str | None = None,
        *,
        force_refresh: bool = False,
    ) -> object:
        """
        Get from cache or set using callback if not found.

        Implements Request Coalescing (SingleFlight) to prevent Thundering Herd.
        Uses thread-safe lock creation with LRU eviction to prevent memory leaks.
        """
        full_key = self._build_key(key, namespace)

        # 1. Optimistic Check (Fast Path)
        if not force_refresh:
            try:
                cached = await self.get(key, namespace)
                if cached is not None:
                    return cached
            except BASE_EXCEPTION as e:
                logger.warning("Failed to retrieve from cache: %s", e)

        # 2. Acquire Lock for this key (thread-safe with LRU eviction)
        lock = self._get_or_create_lock(full_key)

        async with lock:
            # 3. Double Check after acquiring lock (in case another req filled it)
            if not force_refresh:
                cached = await self.get(key, namespace)
                if cached is not None:
                    return cached

            # 4. Execute Callback (Heavy Operation)
            value = await callback()
            await self.set(key, value, ttl, namespace)

            return value

    async def _fallback_to_memory(self) -> None:
        """
        Fallback to in-memory cache when Redis fails at runtime.

        This implements a simple circuit breaker pattern.
        """
        if self.is_redis_available:
            logger.warning("Redis connection lost. Falling back to in-memory cache.")
            self._client = self.memory_client
            self.is_redis_available = False
            # Ensure memory client is running
            if not self.memory_client.is_connected:
                await self.memory_client.start_lifecycle()

    async def disable_redis(self) -> CacheToggleResponse:
        """
        Disable Redis and switch to in-memory cache.

        Returns:
            Dictionary with status and message.
        """
        if not self.is_redis_available:
            return CacheToggleResponse(
                status="unchanged",
                message="Redis is already disabled. Using in-memory cache.",
                backend="in-memory",
                status_code=status.HTTP_200_OK,
            )

        # Disconnect from Redis
        await self.redis_client.disconnect()

        # Switch to in-memory client
        self._client = self.memory_client
        self.is_redis_available = False

        # Ensure memory client is running
        if not self.memory_client.is_connected:
            await self.memory_client.start_lifecycle()

        logger.info("Redis disabled. Switched to in-memory cache.")
        return CacheToggleResponse(
            status="success",
            message="Redis disabled successfully. Using in-memory cache.",
            backend="in-memory",
            status_code=status.HTTP_200_OK,
        )

    async def enable_redis(self) -> CacheToggleResponse:
        """
        Enable Redis and switch from in-memory cache.

        Returns:
            Dictionary with status and message.
        """
        if self.is_redis_available:
            return CacheToggleResponse(
                status="unchanged",
                message="Redis is already enabled.",
                backend="redis",
                status_code=status.HTTP_200_OK,
            )

        try:
            await self.redis_client.connect()
            self._client = self.redis_client
            self.is_redis_available = True
            logger.info("Redis enabled. Switched from in-memory cache.")
            return CacheToggleResponse(
                status="success",
                message="Redis enabled successfully.",
                backend="redis",
                status_code=status.HTTP_200_OK,
            )
        except RedisConnectionError as e:
            logger.warning(f"Failed to enable Redis: {e}")
            return CacheToggleResponse(
                status="error",
                message=f"Failed to connect to Redis: {e}",
                backend="in-memory",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    async def _try_reconnect_redis(self) -> bool:
        """
        Attempt to reconnect to Redis.

        Returns:
            True if reconnection was successful.
        """
        if self.is_redis_available:
            return True

        try:
            await self.redis_client.connect()
            self._client = self.redis_client
            self.is_redis_available = True
            logger.info("Successfully reconnected to Redis.")
            return True
        except RedisConnectionError:
            if logger.isEnabledFor(DEBUG):
                logger.debug("Redis reconnection attempt failed.")
            return False

    async def clear(self, namespace: str | None = None) -> int:
        """
        Clear all cache entries, optionally for a namespace.

        Uses batched deletion to ensure memory safety.
        """
        try:
            if self.is_redis_available and isinstance(self._client, RedisClient):
                prefix = self.cache_config.key_prefix
                pattern = f"{prefix}:{namespace}:*" if namespace else f"{prefix}:*"

                deleted_total = 0
                keys_batch: list[str] = []

                # Use the new async iterator
                async for key in self._client.scan_iter(pattern):
                    keys_batch.append(key)

                    if len(keys_batch) >= 1000:
                        await self._client.delete(*keys_batch)
                        deleted_total += len(keys_batch)
                        keys_batch = []

                # Delete remaining
                if keys_batch:
                    await self._client.delete(*keys_batch)
                    deleted_total += len(keys_batch)

                if deleted_total > 0:
                    self.statistics.record_delete()
                    logger.info("Cleared %d keys for pattern '%s'.", deleted_total, pattern)

                self.statistics.reset()
                return deleted_total

            # Fallback for in-memory
            if isinstance(self._client, MemoryClient):
                await self._client.flush_all()
                self.statistics.reset()
                logger.info("In-memory cache cleared (flushed all).")
                return 0
        except RedisConnectionError:
            # Circuit breaker: fallback to memory on Redis failure
            await self._fallback_to_memory()
            return await self.clear(namespace)
        except BASE_EXCEPTION as e:
            logger.exception("Cache clear failed")
            self.statistics.record_error()
            mssg = "Cache clear failed"
            raise CacheKeyError(mssg) from e
        return 0

    async def expire(self, key: str, seconds: int, namespace: str | None = None) -> bool:
        """Set expiration on key."""
        try:
            full_key = self._build_key(key, namespace)
            return await self._client.expire(full_key, seconds)
        except BASE_EXCEPTION as e:
            logger.exception("Cache expire failed for key %s", key)
            self.statistics.record_error()
            mssg = f"Cache expire failed for key {key}"
            raise CacheKeyError(mssg) from e

    async def ttl(self, key: str, namespace: str | None = None) -> int:
        """Get remaining time to live."""
        try:
            full_key = self._build_key(key, namespace)
            return await self._client.ttl(full_key)
        except BASE_EXCEPTION as e:
            logger.exception("Cache ttl check failed for key %s", key)
            self.statistics.record_error()
            mssg = f"Cache ttl check failed for key {key}"
            raise CacheKeyError(mssg) from e

    async def ping(self) -> bool:
        """Ping the cache server."""
        try:
            return await self._client.ping()
        except BASE_EXCEPTION:
            logger.exception("Cache ping failed")
            return False

    async def health_check(self) -> dict[str, Any]:
        """
        Perform a comprehensive health check.

        Returns:
            Dictionary with health status and details.
        """
        result: dict[str, Any] = {
            "backend": "redis" if self.is_redis_available else "in-memory",
            "statistics": self.get_statistics(),
        }

        try:
            if self.is_redis_available and isinstance(self._client, RedisClient):
                result.update(await self._client.health_check())
            else:
                result["status"] = "healthy" if await self._client.ping() else "unhealthy"
                result["info"] = await self._client.info()
        except BASE_EXCEPTION as e:
            result["status"] = "unhealthy"
            result["error"] = str(e)

        return result

    def get_statistics(self) -> CacheStatisticsData:
        """Get cache statistics."""
        return self.statistics.to_dict()

    def reset_statistics(self) -> None:
        """Reset cache statistics."""
        self.statistics.reset()
        logger.info("Cache statistics reset.")
