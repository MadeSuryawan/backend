"""Custom exceptions for caching module."""

from logging import getLogger

from starlette import status

from app.configs import file_logger
from app.errors import BaseAppError, create_exception_handler

logger = file_logger(getLogger(__name__))


class CacheExceptionError(BaseAppError):
    """Base exception for cache operations."""

    def __init__(self, msg: str = "Cache exception occurred") -> None:
        super().__init__(
            msg=msg,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class CacheKeyError(CacheExceptionError):
    """Raised when cache key operation fails."""

    def __init__(self, msg: str = "Cache key error") -> None:
        super().__init__(msg)
        self.msg = msg
        self.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class CacheSerializationError(CacheExceptionError):
    """Raised when cache serialization fails."""

    def __init__(self, msg: str = "Cannot serialize value") -> None:
        super().__init__(msg)
        self.msg = msg
        self.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class CacheDeserializationError(CacheExceptionError):
    """Raised when cache deserialization fails."""

    def __init__(self, msg: str = "Cannot deserialize value") -> None:
        super().__init__(msg)
        self.msg = msg
        self.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class CacheCompressionError(CacheExceptionError):
    """Raised when cache compression fails."""

    def __init__(self, msg: str = "Cannot compress data") -> None:
        super().__init__(msg)
        self.msg = msg
        self.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class CacheDecompressionError(CacheExceptionError):
    """Raised when cache decompression fails."""

    def __init__(self, msg: str = "Cannot decompress data") -> None:
        super().__init__(msg)
        self.msg = msg
        self.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class RateLimitError(CacheExceptionError):
    """Raised when rate limit is exceeded."""

    def __init__(self, msg: str = "Rate limit exceeded") -> None:
        super().__init__(msg)
        self.msg = msg
        self.status_code = status.HTTP_429_TOO_MANY_REQUESTS


# Create the exception handler using the helper
cache_exception_handler = create_exception_handler(logger)
