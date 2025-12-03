"""Custom exceptions for caching module."""

from logging import getLogger

from starlette import status

from app.configs import file_logger
from app.errors import BaseAppError, create_exception_handler

logger = file_logger(getLogger(__name__))


class CacheExceptionError(BaseAppError):
    """Base exception for cache operations."""

    def __init__(self, detail: str = "Cache exception occurred") -> None:
        super().__init__(
            detail=detail,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class CacheKeyError(CacheExceptionError):
    """Raised when cache key operation fails."""

    def __init__(self, detail: str = "Cache key error") -> None:
        super().__init__(detail)


class CacheSerializationError(CacheExceptionError):
    """Raised when cache serialization fails."""

    def __init__(self, detail: str = "Cannot serialize value") -> None:
        super().__init__(detail)


class CacheDeserializationError(CacheExceptionError):
    """Raised when cache deserialization fails."""

    def __init__(self, detail: str = "Cannot deserialize value") -> None:
        super().__init__(detail)


class CacheCompressionError(CacheExceptionError):
    """Raised when cache compression fails."""

    def __init__(self, detail: str = "Cannot compress data") -> None:
        super().__init__(detail)


class CacheDecompressionError(CacheExceptionError):
    """Raised when cache decompression fails."""

    def __init__(self, detail: str = "Cannot decompress data") -> None:
        super().__init__(detail)


# Create the exception handler using the helper
cache_exception_handler = create_exception_handler(logger)
