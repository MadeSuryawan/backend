"""Protocol definitions for cache client implementations."""

from collections.abc import Awaitable
from logging import DEBUG
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CacheClientProtocol(Protocol):
    """
    Protocol for cache client implementations.

    This protocol defines the interface that all cache clients must implement.
    Both RedisClient and MemoryClient conform to this protocol.

    Note: All methods return Awaitable to be compatible with both sync-wrapped
    and native async implementations.
    """

    def get(self, key: str) -> Awaitable[str | None]:
        """Get a value from the cache."""
        ...

    def set(self, key: str, value: str, ex: int | None = None) -> Awaitable[bool]:
        """Set a value in the cache with optional TTL."""
        ...

    def delete(self, *keys: str) -> Awaitable[int]:
        """Delete one or more keys from the cache."""
        ...

    def exists(self, *keys: str) -> Awaitable[int]:
        """Check if keys exist in the cache."""
        ...

    def expire(self, key: str, seconds: int) -> Awaitable[bool]:
        """Set an expiration time on a key."""
        ...

    def ttl(self, key: str) -> Awaitable[int]:
        """Get the remaining TTL of a key."""
        ...

    def ping(self) -> Awaitable[bool]:
        """Check if the cache server is reachable."""
        ...

    def info(self) -> Awaitable[dict[str, Any]]:
        """Get information about the cache."""
        ...

    def flush_all(self) -> Awaitable[bool]:
        """Clear all entries from the cache."""
        ...


def is_debug_enabled(logger_level: int) -> bool:
    """Check if debug logging is enabled without evaluating log arguments."""
    return logger_level <= DEBUG
