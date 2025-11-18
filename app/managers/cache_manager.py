"""Main cache manager for Redis caching operations."""

from collections.abc import Awaitable, Callable, Coroutine
from logging import getLogger
from typing import Any

from redis.exceptions import ConnectionError as RedisConnectionError

from app.clients.memory_client import MemoryClient
from app.clients.redis_client import RedisClient
from app.configs.settings import CacheConfig
from app.data.statistics import CacheStatistics
from app.utils import (
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
    """Main cache manager for Redis operations with advanced features."""

    def __init__(self) -> None:
        """Initialize cache manager."""
        self.redis_client = RedisClient()
        self.memory_client = MemoryClient()
        self._client: RedisClient | MemoryClient = self.redis_client
        self.is_redis_available = False
        self.cache_config = CacheConfig()
        self.statistics = CacheStatistics()

    async def initialize(self) -> None:
        """Initialize cache manager by connecting to Redis.

        If the Redis connection fails, it falls back to an in-memory cache.
        """
        try:
            await self.redis_client.connect()
            self._client = self.redis_client
            self.is_redis_available = True
        except RedisConnectionError as e:
            logger.warning(f"Redis connection failed: {e}. Falling back to in-memory cache.")
            self._client = self.memory_client
            self.is_redis_available = False
        logger.info("Cache manager initialized successfully.")

    async def shutdown(self) -> None:
        """Shutdown cache manager by closing the client connection."""
        if isinstance(self._client, RedisClient):
            await self._client.disconnect()
        elif isinstance(self._client, MemoryClient):
            await self._client.close()
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

            return deserialize(cached_value)
        except Exception:
            logger.exception(f"Cache get failed for key {key}")
            self.statistics.record_error()
            raise

    async def set(
        self,
        key: str,
        value: dict[str, Any],
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

            result = await self._client.set(full_key, serialized, ex=ex)
            self.statistics.record_set(len(serialized.encode("utf-8")))
        except Exception:
            logger.exception(f"Cache set failed for key {key}")
            self.statistics.record_error()
            raise
        return result

    async def delete(self, *keys: str, namespace: str | None = None) -> int:
        """Delete keys from cache."""
        try:
            full_keys = [self._build_key(key, namespace) for key in keys]
            deleted_count = await self._client.delete(*full_keys)
            self.statistics.record_delete()
        except Exception:
            logger.exception("Cache delete failed")
            self.statistics.record_error()
            raise
        return deleted_count

    async def exists(self, *keys: str, namespace: str | None = None) -> int:
        """Check if keys exist."""
        try:
            full_keys = [self._build_key(key, namespace) for key in keys]
            return await self._client.exists(*full_keys)
        except Exception:
            logger.exception("Cache exists check failed")
            self.statistics.record_error()
            raise

    async def get_or_set(
        self,
        key: str,
        callback: CacheCallback,
        ttl: int | None = None,
        namespace: str | None = None,
        *,
        force_refresh: bool = False,
    ) -> object:
        """Get from cache or set using callback if not found."""
        if not force_refresh:
            try:
                cached = await self.get(key, namespace)
                if cached is not None:
                    return cached
            except RedisConnectionError as e:
                logger.warning(f"Failed to retrieve from cache: {e}")

        # Call callback
        value = await callback()
        await self.set(key, value, ttl, namespace)
        return value

    async def clear(self, namespace: str | None = None) -> int:
        """Clear all cache entries, optionally for a namespace."""
        try:
            if self.is_redis_available and isinstance(self._client, RedisClient):
                prefix = self.cache_config.key_prefix
                pattern = f"{prefix}:{namespace}:*" if namespace else f"{prefix}:*"
                # Use scan_keys to get all matching keys
                all_keys = []
                cursor = 0
                while True:
                    cursor, keys = await self._client.scan_keys(pattern, cursor=cursor)
                    all_keys.extend(keys)
                    if cursor == 0:
                        break

                if all_keys:
                    deleted_count = await self._client.delete(*all_keys)
                    self.statistics.record_delete()
                    logger.info(f"Cleared {deleted_count} keys for pattern '{pattern}'.")
                self.statistics.reset()  # Reset statistics after clearing Redis cache
                return len(all_keys) if all_keys else 0

            # Fallback for in-memory or if Redis is unavailable
            if isinstance(self._client, MemoryClient):
                await self._client.flush_all()
                self.statistics.reset()
                logger.info("In-memory cache cleared (flushed all).")
                return 0  # MemoryClient flush_all doesn't return count
        except Exception:
            logger.exception("Cache clear failed")
            self.statistics.record_error()
            raise
        return 0

    async def expire(self, key: str, seconds: int, namespace: str | None = None) -> bool:
        """Set expiration on key.

        Args:
            key: Cache key.
            seconds: Expiration time in seconds.
            namespace: Optional namespace.

        Returns:
            True if timeout was set.
        """
        try:
            full_key = self._build_key(key, namespace)
            return await self._client.expire(full_key, seconds)
        except Exception:
            logger.exception(f"Cache expire failed for key {key}")
            self.statistics.record_error()
            raise

    async def ttl(self, key: str, namespace: str | None = None) -> int:
        """Get remaining time to live.

        Args:
            key: Cache key.
            namespace: Optional namespace.

        Returns:
            TTL in seconds, -1 if no expiration, -2 if key doesn't exist.
        """
        try:
            full_key = self._build_key(key, namespace)
            return await self._client.ttl(full_key)
        except Exception:
            logger.exception(f"Cache ttl check failed for key {key}")
            self.statistics.record_error()
            raise

    async def ping(self) -> bool | Awaitable[bool]:
        """Ping the cache server.

        Returns:
            True if the server is reachable.
        """
        try:
            return await self._client.ping()
        except Exception:
            logger.exception("Cache ping failed")
            return False

    def get_statistics(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary of cache statistics.
        """
        return self.statistics.to_dict()

    def reset_statistics(self) -> None:
        """Reset cache statistics."""
        self.statistics.reset()
        logger.info("Cache statistics reset.")


cache_manager = CacheManager()
