# app/clients/redis_client.py
"""Redis client module for cache operations with retry logic and health checks."""

from collections.abc import AsyncGenerator, Awaitable
from logging import DEBUG, getLogger
from time import monotonic
from typing import Any

from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError

from app.configs import pool_kwargs
from app.decorators.with_retry import RETRIABLE_EXCEPTIONS, with_retry
from app.utils.helpers import file_logger

logger = file_logger(getLogger(__name__))


class RedisClient:
    """
    Async Redis client wrapper with connection pooling, retry logic, and health checks.

    Features:
        - Automatic retry with exponential backoff for transient failures
        - Proper connection pool cleanup on disconnect
        - Health check endpoint for monitoring
        - Memory-efficient key scanning
    """

    def __init__(self) -> None:
        """Initialize Redis client."""
        self.config = pool_kwargs
        self._pool: ConnectionPool | None = None
        self._redis: Redis | None = None

    async def connect(self) -> None:
        """Establish Redis connection pool."""
        try:
            self._pool = ConnectionPool(**self.config)
            self._redis = Redis(connection_pool=self._pool)
            # Test connection with ping
            ping_result = self._redis.ping()
            if isinstance(ping_result, Awaitable):
                result = await ping_result
            else:
                result = ping_result
            if not result:
                mssg = "Redis ping returned False"
                raise RedisConnectionError(mssg)
            logger.info("Redis connection successful. Cache is using Redis.")
        except RETRIABLE_EXCEPTIONS + (RedisError,) as e:
            logger.exception("Failed to connect to Redis")
            mssg = f"Cannot connect to Redis at {self.config.get('host')}:{self.config.get('port')}"
            raise RedisConnectionError(mssg) from e

    async def disconnect(self) -> None:
        """Close Redis connection pool properly."""
        if self._redis is not None:
            await self._redis.close()
            self._redis = None
        if self._pool is not None:
            await self._pool.disconnect()
            self._pool = None
        logger.info("Redis connection and pool closed.")

    @property
    def client(self) -> Redis:
        """Get Redis client instance."""
        if self._redis is None:
            mssg = "Redis client not initialized. Call connect() first."
            raise RuntimeError(mssg)
        return self._redis

    @with_retry(max_retries=3, base_delay=0.1)
    async def get(self, key: str) -> str | None:
        """Get value from cache with automatic retry."""
        try:
            return await self.client.get(key)
        except RedisError as e:
            if logger.isEnabledFor(DEBUG):
                logger.debug("Failed to get key %s: %s", key, e)
            mssg = f"Cache get operation failed for key {key}: {e}"
            raise RedisConnectionError(mssg) from e

    @with_retry(max_retries=3, base_delay=0.1)
    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        """Set value in cache with automatic retry."""
        try:
            return bool(await self.client.set(key, value, ex=ex))
        except RedisError as e:
            if logger.isEnabledFor(DEBUG):
                logger.debug("Failed to set key %s: %s", key, e)
            mssg = f"Cache set operation failed for key {key}: {e}"
            raise RedisConnectionError(mssg) from e

    @with_retry(max_retries=3, base_delay=0.1)
    async def delete(self, *keys: str) -> int:
        """Delete keys from cache with automatic retry."""
        if not keys:
            return 0
        try:
            return await self.client.delete(*keys)
        except RedisError as e:
            logger.exception("Failed to delete keys")
            mssg = f"Cache delete operation failed for keys {keys}: {e}"
            raise RedisConnectionError(mssg) from e

    @with_retry(max_retries=3, base_delay=0.1)
    async def exists(self, *keys: str) -> int:
        """Check if keys exist in cache with automatic retry."""
        try:
            return await self.client.exists(*keys)
        except RedisError as e:
            logger.exception("Failed to check key existence")
            mssg = f"Cache exists operation failed for keys {keys}: {e}"
            raise RedisConnectionError(mssg) from e

    @with_retry(max_retries=3, base_delay=0.1)
    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration on key with automatic retry."""
        try:
            return await self.client.expire(key, seconds)
        except RedisError as e:
            if logger.isEnabledFor(DEBUG):
                logger.debug("Failed to set expiration on %s: %s", key, e)
            mssg = f"Cache expire operation failed for key {key}: {e}"
            raise RedisConnectionError(mssg) from e

    @with_retry(max_retries=3, base_delay=0.1)
    async def ttl(self, key: str) -> int:
        """Get remaining time to live with automatic retry."""
        try:
            return await self.client.ttl(key)
        except RedisError as e:
            if logger.isEnabledFor(DEBUG):
                logger.debug("Failed to get TTL for %s: %s", key, e)
            mssg = f"Cache ttl operation failed for key {key}: {e}"
            raise RedisConnectionError(mssg) from e

    @with_retry(max_retries=3, base_delay=0.1)
    async def incr(self, key: str) -> int:
        """Increment value atomically with automatic retry."""
        try:
            return await self.client.incr(key)
        except RedisError as e:
            if logger.isEnabledFor(DEBUG):
                logger.debug("Failed to increment key %s: %s", key, e)
            mssg = f"Cache incr operation failed for key {key}: {e}"
            raise RedisConnectionError(mssg) from e

    async def flush_db(self) -> bool:
        """Flush current database."""
        try:
            return await self.client.flushdb()
        except RedisError as e:
            logger.exception("Failed to flush database")
            mssg = f"Cache flush_db operation failed: {e}"
            raise RedisConnectionError(mssg) from e

    async def flush_all(self) -> bool:
        """Flush all databases (alias for flush_db for protocol compatibility)."""
        return await self.flush_db()

    async def ping(self) -> bool:
        """Ping Redis server."""
        try:
            ping_result = self.client.ping()
            if isinstance(ping_result, Awaitable):
                result = await ping_result
            else:
                result = ping_result
            return bool(result)
        except RedisError as e:
            logger.exception("Failed to ping Redis")
            mssg = f"Cache ping operation failed: {e}"
            raise RedisConnectionError(mssg) from e

    async def info(self) -> dict[str, Any]:
        """Get Redis server info."""
        try:
            info = await self.client.info()
            return info if isinstance(info, dict) else {}
        except RedisError as e:
            logger.exception("Failed to get server info")
            mssg = f"Cache info operation failed: {e}"
            raise RedisConnectionError(mssg) from e

    async def health_check(self) -> dict[str, Any]:
        """
        Perform a comprehensive health check.

        Returns:
            Dictionary with health status, latency, and server info.
        """
        try:
            start = monotonic()
            await self.ping()
            latency_ms = (monotonic() - start) * 1000

            info = await self.info()
            return {
                "status": "healthy",
                "latency_ms": round(latency_ms, 2),
                "connected_clients": info.get("connected_clients"),
                "used_memory_human": info.get("used_memory_human"),
                "uptime_seconds": info.get("uptime_in_seconds"),
                "redis_version": info.get("redis_version"),
            }
        except RedisError as e:
            return {
                "status": "unhealthy",
                "error": str(e),
            }

    async def scan_iter(self, pattern: str, count: int = 100) -> AsyncGenerator[str]:
        """
        Yield keys matching the pattern memory-efficiently.

        Args:
            pattern: Glob-style pattern to match keys.
            count: Hint for number of keys to return per iteration.

        Yields:
            Keys matching the pattern.
        """
        cursor: int = 0
        while True:
            try:
                scan_result: tuple[int, list[bytes | str]] = await self.client.scan(
                    cursor,
                    match=pattern,
                    count=count,
                )
                cursor, keys = scan_result

                for key in keys:
                    yield key.decode("utf-8") if isinstance(key, bytes) else key

                if cursor == 0:
                    break

            except RedisError as e:
                logger.exception("Failed to scan keys with pattern %s", pattern)
                mssg = f"Cache scan_iter operation failed for pattern {pattern}: {e}"
                raise RedisConnectionError(mssg) from e
