# app/clients/redis_client.py
"""Redis client module for cache operations."""

from collections.abc import Awaitable
from logging import getLogger
from typing import Any

from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.configs.settings import pool_kwargs
from app.utils.helpers import file_logger

logger = file_logger(getLogger(__name__))


class RedisClient:
    """Async Redis client wrapper with connection pooling."""

    def __init__(self) -> None:
        """
        Initialize Redis client.

        Defaults to RedisCacheConfig().

        Raises:
            ValueError: If configuration is invalid.
        """
        self.config = pool_kwargs
        self._pool: ConnectionPool | None = None
        self._redis: Redis | None = None

    async def connect(self) -> None:
        """
        Establish Redis connection pool.

        Raises:
            RedisConnectionError: If connection fails.
        """
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
            mssg = f"Cannot connect to Redis at {self.config['host']}:{self.config['port']}"
            raise RedisConnectionError(mssg) from e

    async def disconnect(self) -> None:
        """Close Redis connection pool."""
        if self._redis is not None:
            await self._redis.close()
            logger.info("Redis connection closed.")

    @property
    def client(self) -> Redis:
        """
        Get Redis client.

        Returns:
            Redis client instance.

        Raises:
            RuntimeError: If client is not initialized.
        """
        if self._redis is None:
            mssg = "Redis client not initialized. Call connect() first."
            raise RuntimeError(mssg)
        return self._redis

    async def get(self, key: str) -> str | None:
        """
        Get value from cache.

        Args:
            key: Cache key.

        Returns:
            Cached value or None.

        Raises:
            RedisConnectionError: If operation fails.
        """
        try:
            return await self.client.get(key)
        except RedisError as e:
            logger.exception(f"Failed to get key {key}")
            mssg = f"Cache get operation failed for key {key}: {e}"
            raise RedisConnectionError(mssg) from e

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key.
            value: Value to cache.
            ex: Expiration time in seconds.

        Returns:
            True if successful.

        Raises:
            RedisConnectionError: If operation fails.
        """
        try:
            return bool(await self.client.set(key, value, ex=ex))
        except RedisError as e:
            logger.exception(f"Failed to set key {key}")
            mssg = f"Cache set operation failed for key {key}: {e}"
            raise RedisConnectionError(mssg) from e

    async def delete(self, *keys: str) -> int:
        """
        Delete keys from cache.

        Args:
            *keys: Cache keys to delete.

        Returns:
            Number of keys deleted.

        Raises:
            RedisConnectionError: If operation fails.
        """
        try:
            return await self.client.delete(*keys)
        except RedisError as e:
            logger.exception("Failed to delete keys")
            mssg = f"Cache delete operation failed for keys {keys}: {e}"
            raise RedisConnectionError(mssg) from e

    async def exists(self, *keys: str) -> int:
        """
        Check if keys exist in cache.

        Args:
            *keys: Cache keys to check.

        Returns:
            Number of keys that exist.

        Raises:
            RedisConnectionError: If operation fails.
        """
        try:
            return await self.client.exists(*keys)
        except RedisError as e:
            logger.exception("Failed to check key existence")
            mssg = f"Cache exists operation failed for keys {keys}: {e}"
            raise RedisConnectionError(mssg) from e

    async def expire(self, key: str, seconds: int) -> bool:
        """
        Set expiration on key.

        Args:
            key: Cache key.
            seconds: Expiration time in seconds.

        Returns:
            True if timeout was set.

        Raises:
            RedisConnectionError: If operation fails.
        """
        try:
            return await self.client.expire(key, seconds)
        except RedisError as e:
            logger.exception(f"Failed to set expiration on {key}")
            mssg = f"Cache expire operation failed for key {key}: {e}"
            raise RedisConnectionError(mssg) from e

    async def ttl(self, key: str) -> int:
        """
        Get remaining time to live.

        Args:
            key: Cache key.

        Returns:
            TTL in seconds, -1 if no expiration, -2 if key doesn't exist.

        Raises:
            RedisConnectionError: If operation fails.
        """
        try:
            return await self.client.ttl(key)
        except RedisError as e:
            logger.exception(f"Failed to get TTL for {key}")
            mssg = f"Cache ttl operation failed for key {key}: {e}"
            raise RedisConnectionError(mssg) from e

    async def flush_db(self) -> bool:
        """
        Flush current database.

        Returns:
            True if successful.

        Raises:
            RedisConnectionError: If operation fails.
        """
        try:
            return await self.client.flushdb()
        except RedisError as e:
            logger.exception("Failed to flush database")
            mssg = f"Cache flush_db operation failed: {e}"
            raise RedisConnectionError(mssg) from e

    async def ping(self) -> bool:
        """
        Ping Redis server.

        Returns:
            True if server is reachable.

        Raises:
            RedisConnectionError: If operation fails.
        """
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

    async def scan_keys(self, pattern: str, cursor: int = 0) -> tuple[int, list[str]]:
        """
        Scan keys in the Redis database using the SCAN command.

        Args:
            pattern: Pattern to match keys against.
            cursor: The cursor position to start scanning from.

        Returns:
            A tuple containing the new cursor and a list of keys found in this iteration.

        Raises:
            RedisConnectionError: If operation fails.
        """
        try:
            new_cursor, keys = await self.client.scan(cursor, match=pattern)
            return int(new_cursor), [
                key.decode("utf-8") if isinstance(key, bytes) else key for key in keys
            ]
        except RedisError as e:
            logger.exception(f"Failed to scan keys with pattern {pattern}")
            mssg = f"Cache scan_keys operation failed for pattern {pattern}: {e}"
            raise RedisConnectionError(mssg) from e
