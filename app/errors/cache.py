"""Custom exceptions for caching module."""


class CacheExceptionError(Exception):
    """Base exception for cache operations."""


class RedisConnectionError(CacheExceptionError):
    """Raised when Redis connection fails."""


class CacheKeyError(CacheExceptionError):
    """Raised when cache key operation fails."""


class CacheSerializationError(CacheExceptionError):
    """Raised when cache serialization fails."""


class CacheDeserializationError(CacheExceptionError):
    """Raised when cache deserialization fails."""


class CacheCompressionError(CacheExceptionError):
    """Raised when cache compression fails."""


class CacheDecompressionError(CacheExceptionError):
    """Raised when cache decompression fails."""


class RateLimitError(CacheExceptionError):
    """Raised when rate limit is exceeded."""
