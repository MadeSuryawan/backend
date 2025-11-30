from app.errors.base import BASE_EXCEPTION, BaseAppError, create_exception_handler
from app.errors.cache import (
    CacheCompressionError,
    CacheDecompressionError,
    CacheDeserializationError,
    CacheExceptionError,
    CacheKeyError,
    CacheSerializationError,
    RateLimitError,
    cache_exception_handler,
)
from app.errors.email import (
    AuthenticationError,
    ConfigurationError,
    EmailServiceError,
    SendingError,
    email_service_exception_handler,
)

__all__ = [
    "AuthenticationError",
    "ConfigurationError",
    "EmailServiceError",
    "SendingError",
    "CacheCompressionError",
    "CacheDecompressionError",
    "CacheDeserializationError",
    "CacheExceptionError",
    "CacheKeyError",
    "CacheSerializationError",
    "RateLimitError",
    "BASE_EXCEPTION",
    "email_service_exception_handler",
    "cache_exception_handler",
    "create_exception_handler",
    "BaseAppError",
]
