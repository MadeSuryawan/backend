# app/managers/cache_manager.py
"""Main cache manager for Redis caching operations."""

from asyncio import Lock
from collections.abc import Callable, Coroutine
from logging import getLogger
from typing import Any

from pydantic_core import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError

from app.clients import MemoryClient, RedisClient
from app.configs import CacheConfig, file_logger
from app.data import CacheStatistics
from app.errors import BASE_EXCEPTION, CacheDeserializationError, CacheKeyError
from app.utils import (
    compress,
    decompress,
    deserialize,
    do_compress,
    serialize,
)

logger = file_logger(getLogger(__name__))


CacheCallback = Callable[..., Coroutine[Any, Any, Any]]


class CacheManager:
    """Main cache manager for Redis operations with advanced features."""

    def __init__(self) -> None:
        """Initialize cache manager."""
        self.redis_client = RedisClient()
        self.memory_client = MemoryClient()
        self._client: RedisClient | MemoryClient = self.redis_client
        self.is_redis_available = False
        self.cache_config = CacheConfig()
        self.statistics = CacheStatistics()
        # Locks for request coalescing (Thundering Herd protection)
        self._locks: dict[str, Lock] = {}

    async def initialize(self) -> None:
        """
        Initialize cache manager by connecting to Redis.

        If the Redis connection fails, it falls back to an in-memory cache.
        """
        try:
            await self.redis_client.connect()
            self._client = self.redis_client
            self.is_redis_available = True
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
            logger.debug(f"Getting from cache: {full_key}")
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
            logger.exception(f"Cache get failed for key: {key}")
            self.statistics.record_error()
            mssg = f"Cache get failed for key {key}, {e}"
            raise CacheKeyError(mssg) from e

    async def set(
        self,
        key: str,
        value: dict,
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
            logger.exception(f"Cache set failed for key {key}")
            self.statistics.record_error()
            mssg = f"Cache set failed for key {key}"
            raise CacheKeyError(mssg) from e
        return success

    async def delete(self, *keys: str, namespace: str | None = None) -> int:
        """Delete keys from cache."""
        try:
            full_keys = [self._build_key(key, namespace) for key in keys]
            deleted_count = await self._client.delete(*full_keys)
            self.statistics.record_delete()
        except BASE_EXCEPTION as e:
            logger.exception("Cache delete failed")
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
            logger.exception("Cache exists check failed")
            self.statistics.record_error()
            mssg = "Cache exists check failed"
            raise CacheKeyError(mssg) from e

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
        """
        full_key = self._build_key(key, namespace)

        # 1. Optimistic Check (Fast Path)
        if not force_refresh:
            try:
                cached = await self.get(key, namespace)
                if cached is not None:
                    return cached
            except BASE_EXCEPTION as e:
                logger.warning(f"Failed to retrieve from cache: {e}")

        # 2. Acquire Lock for this key
        if full_key not in self._locks:
            self._locks[full_key] = Lock()

        async with self._locks[full_key]:
            # 3. Double Check after acquiring lock (in case another req filled it)
            if not force_refresh:
                cached = await self.get(key, namespace)
                if cached is not None:
                    return cached

            # 4. Execute Callback (Heavy Operation)
            value = await callback()
            await self.set(key, value, ttl, namespace)

            # Optional: Cleanup lock to prevent memory growth?
            # We leave it for now as Python's dict is efficient enough for moderate key counts.
            return value

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
                keys_batch = []

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
                    logger.info(f"Cleared {deleted_total} keys for pattern '{pattern}'.")

                self.statistics.reset()
                return deleted_total

            # Fallback for in-memory
            if isinstance(self._client, MemoryClient):
                await self._client.flush_all()
                self.statistics.reset()
                logger.info("In-memory cache cleared (flushed all).")
                return 0
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
            logger.exception(f"Cache expire failed for key {key}")
            self.statistics.record_error()
            mssg = f"Cache expire failed for key {key}"
            raise CacheKeyError(mssg) from e

    async def ttl(self, key: str, namespace: str | None = None) -> int:
        """Get remaining time to live."""
        try:
            full_key = self._build_key(key, namespace)
            return await self._client.ttl(full_key)
        except BASE_EXCEPTION as e:
            logger.exception(f"Cache ttl check failed for key {key}")
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

    def get_statistics(self) -> dict[str, Any]:
        """Get cache statistics."""
        return self.statistics.to_dict()

    def reset_statistics(self) -> None:
        """Reset cache statistics."""
        self.statistics.reset()
        logger.info("Cache statistics reset.")


cache_manager = CacheManager()
