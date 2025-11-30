# app/clients/redis_client.py
"""Redis client module for cache operations."""

from collections.abc import AsyncGenerator, Awaitable
from logging import getLogger
from typing import Any

from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.configs import file_logger, pool_kwargs

logger = file_logger(getLogger(__name__))


class RedisClient:
    """Async Redis client wrapper with connection pooling."""

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
        except (ConnectionError, RedisTimeoutError, RedisError) as e:
            logger.exception("Failed to connect to Redis")
            mssg = f"Cannot connect to Redis at {self.config.get('host')}:{self.config.get('port')}"
            raise RedisConnectionError(mssg) from e

    async def disconnect(self) -> None:
        """Close Redis connection pool."""
        if self._redis is not None:
            await self._redis.close()
            logger.info("Redis connection closed.")

    @property
    def client(self) -> Redis:
        """Get Redis client instance."""
        if self._redis is None:
            mssg = "Redis client not initialized. Call connect() first."
            raise RuntimeError(mssg)
        return self._redis

    async def get(self, key: str) -> str | None:
        """Get value from cache."""
        try:
            return await self.client.get(key)
        except RedisError as e:
            logger.exception(f"Failed to get key {key}")
            mssg = f"Cache get operation failed for key {key}: {e}"
            raise RedisConnectionError(mssg) from e

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        """Set value in cache."""
        try:
            return bool(await self.client.set(key, value, ex=ex))
        except RedisError as e:
            logger.exception(f"Failed to set key {key}")
            mssg = f"Cache set operation failed for key {key}: {e}"
            raise RedisConnectionError(mssg) from e

    async def delete(self, *keys: str) -> int:
        """Delete keys from cache."""
        if not keys:
            return 0
        try:
            return await self.client.delete(*keys)
        except RedisError as e:
            logger.exception("Failed to delete keys")
            mssg = f"Cache delete operation failed for keys {keys}: {e}"
            raise RedisConnectionError(mssg) from e

    async def exists(self, *keys: str) -> int:
        """Check if keys exist in cache."""
        try:
            return await self.client.exists(*keys)
        except RedisError as e:
            logger.exception("Failed to check key existence")
            mssg = f"Cache exists operation failed for keys {keys}: {e}"
            raise RedisConnectionError(mssg) from e

    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration on key."""
        try:
            return await self.client.expire(key, seconds)
        except RedisError as e:
            logger.exception(f"Failed to set expiration on {key}")
            mssg = f"Cache expire operation failed for key {key}: {e}"
            raise RedisConnectionError(mssg) from e

    async def ttl(self, key: str) -> int:
        """Get remaining time to live."""
        try:
            return await self.client.ttl(key)
        except RedisError as e:
            logger.exception(f"Failed to get TTL for {key}")
            mssg = f"Cache ttl operation failed for key {key}: {e}"
            raise RedisConnectionError(mssg) from e

    async def flush_db(self) -> bool:
        """Flush current database."""
        try:
            return await self.client.flushdb()
        except RedisError as e:
            logger.exception("Failed to flush database")
            mssg = f"Cache flush_db operation failed: {e}"
            raise RedisConnectionError(mssg) from e

    async def ping(self) -> bool:
        """Ping Redis server."""
        try:
            ping_result = self.client.ping()
            if isinstance(ping_result, Awaitable):
                return await ping_result
        except RedisError as e:
            logger.exception("Failed to ping Redis")
            mssg = f"Cache ping operation failed: {e}"
            raise RedisConnectionError(mssg) from e
        return ping_result

    async def info(self) -> dict[str, Any]:
        """Get Redis server info."""
        try:
            info = await self.client.info()
            return info if isinstance(info, dict) else {}
        except RedisError as e:
            logger.exception("Failed to get server info")
            mssg = f"Cache info operation failed: {e}"
            raise RedisConnectionError(mssg) from e

    async def scan_iter(self, pattern: str, count: int = 100) -> AsyncGenerator[str]:
        """
        Yield keys matching the pattern memory-efficiently.

        Replaces the old scan_keys which loaded all keys into memory.
        """
        # Fix: Start cursor as integer 0
        cursor = 0
        while True:
            try:
                # The scan command accepts and returns an integer cursor
                cursor, keys = await self.client.scan(cursor, match=pattern, count=count)

                for key in keys:
                    yield key.decode("utf-8") if isinstance(key, bytes) else key

                # If cursor is 0, iteration is complete
                if cursor == 0:
                    break

            except RedisError as e:
                logger.exception(f"Failed to scan keys with pattern {pattern}")
                mssg = f"Cache scan_iter operation failed for pattern {pattern}: {e}"
                raise RedisConnectionError(mssg) from e
