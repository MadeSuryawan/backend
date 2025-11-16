"""Main cache manager for Redis caching operations."""

import hashlib
import logging
from collections.abc import Awaitable, Coroutine
from typing import Any

from app.clients.redis_client import RedisClient
from app.configs.config import ApplicationConfig, CacheConfig
from app.errors.exceptions import RedisConnectionError
from app.serializer import CacheSerializer
from app.statistics import CacheStatistics
from app.types.types import CacheCallback, CacheKey

logger = logging.getLogger(__name__)


class CacheManager:
    """Main cache manager for Redis operations with advanced features."""

    def __init__(self) -> None:
        """Initialize cache manager.

        Args:
            config: Application configuration.
        """
        self.config = ApplicationConfig()
        self.redis_client = RedisClient(self.config.redis)
        self.cache_config = self.config.cache
        self.serializer = CacheSerializer()
        self.statistics = CacheStatistics()

    async def initialize(self) -> None:
        """Initialize cache manager by connecting to Redis.

        Raises:
            RedisConnectionError: If connection fails.
        """
        await self.redis_client.connect()
        logger.info("Cache manager initialized successfully.")

    async def shutdown(self) -> None:
        """Shutdown cache manager by closing Redis connection."""
        await self.redis_client.disconnect()
        logger.info("Cache manager shutdown successfully.")

    def _build_key(self, key: str, namespace: str | None = None) -> CacheKey:
        """Build full cache key with prefix and namespace.

        Args:
            key: Base cache key.
            namespace: Optional namespace.

        Returns:
            Full cache key.
        """
        if namespace:
            return f"{self.cache_config.key_prefix}{namespace}:{key}"
        return f"{self.cache_config.key_prefix}{key}"

    def _hash_key(self, key: str) -> str:
        """Generate hash of key for long keys.

        Args:
            key: Cache key.

        Returns:
            SHA256 hash of key.
        """
        return hashlib.sha256(key.encode()).hexdigest()

    async def get(
        self,
        key: str,
        namespace: str | None = None,
    ) -> Any:
        """Get value from cache.

        Args:
            key: Cache key.
            namespace: Optional namespace.

        Returns:
            Cached value or None if not found.
        """
        try:
            full_key = self._build_key(key, namespace)
            cached_value = await self.redis_client.get(full_key)

            if cached_value is None:
                self.statistics.record_miss()
                return None

            self.statistics.record_hit()
            self.statistics.record_read(len(cached_value.encode("utf-8")))

            # Decompress if needed
            if isinstance(cached_value, str):
                cached_value = self.serializer.decompress(cached_value)

            return self.serializer.deserialize(cached_value)
        except Exception:
            logger.exception(f"Cache get failed for key {key}")
            self.statistics.record_error()
            raise

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
        namespace: str | None = None,
        *,
        compress: bool | None = None,
    ) -> bool:
        """Set value in cache.

        Args:
            key: Cache key.
            value: Value to cache.
            ttl: Time to live in seconds. Uses default if not provided.
            namespace: Optional namespace.
            compress: Whether to compress. Uses config setting if not provided.

        Returns:
            True if successful.
        """
        try:
            full_key = self._build_key(key, namespace)
            serialized = self.serializer.serialize(value)

            # Determine compression
            should_compress = (
                compress if compress is not None else self.cache_config.compression_enabled
            )
            if should_compress and self.serializer.should_compress(
                serialized,
                self.cache_config.compression_threshold,
            ):
                serialized = self.serializer.compress(serialized)

            # Set expiration
            ex = ttl if ttl is not None else self.cache_config.default_ttl
            ex = min(ex, self.cache_config.max_ttl)

            result = await self.redis_client.set(full_key, serialized, ex=ex)
            self.statistics.record_set(len(serialized.encode("utf-8")))
        except Exception:
            logger.exception(f"Cache set failed for key {key}")
            self.statistics.record_error()
            raise
        return result

    async def delete(self, *keys: str, namespace: str | None = None) -> int:
        """Delete keys from cache.

        Args:
            *keys: Cache keys to delete.
            namespace: Optional namespace.

        Returns:
            Number of keys deleted.
        """
        try:
            full_keys = [self._build_key(key, namespace) for key in keys]
            deleted_count = await self.redis_client.delete(*full_keys)
            self.statistics.record_delete()
        except Exception:
            logger.exception("Cache delete failed")
            self.statistics.record_error()
            raise
        return deleted_count

    async def exists(self, *keys: str, namespace: str | None = None) -> int:
        """Check if keys exist.

        Args:
            *keys: Cache keys to check.
            namespace: Optional namespace.

        Returns:
            Number of keys that exist.
        """
        try:
            full_keys = [self._build_key(key, namespace) for key in keys]
            return await self.redis_client.exists(*full_keys)
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
    ) -> Coroutine[Any, Any, Any]:
        """Get from cache or set using callback if not found.

        Args:
            key: Cache key.
            callback: Async function to call if cache miss.
            ttl: Time to live in seconds.
            namespace: Optional namespace.
            force_refresh: Force refresh from callback.

        Returns:
            Cached or freshly computed value.
        """
        if not force_refresh:
            try:
                cached = await self.get(key, namespace)
                if cached is not None:
                    return cached
            except RuntimeError as e:
                logger.warning(f"Failed to retrieve from cache: {e}")

        # Call callback
        value = await callback()
        await self.set(key, value, ttl, namespace)
        return value

    async def clear(self, namespace: str | None = None) -> int:
        """Clear all cache entries, optionally for a namespace.

        Args:
            namespace: Optional namespace to clear.

        Returns:
            Number of keys deleted.
        """
        try:
            # For now, flush entire database
            # In production, consider using SCAN pattern matching
            await self.redis_client.flush_db()
            self.statistics.reset()
            logger.info("Cache cleared successfully.")
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
            return await self.redis_client.expire(full_key, seconds)
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
            return await self.redis_client.ttl(full_key)
        except Exception:
            logger.exception(f"Cache ttl check failed for key {key}")
            self.statistics.record_error()
            raise

    async def ping(self) -> bool | Awaitable[bool]:
        """Ping Redis server.

        Returns:
            True if server is reachable.
        """
        try:
            return await self.redis_client.ping()
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
