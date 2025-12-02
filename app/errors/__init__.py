from app.errors.base import BASE_EXCEPTION, BaseAppError, create_exception_handler
from app.errors.cache import (
    CacheCompressionError,
    CacheDecompressionError,
    CacheDeserializationError,
    CacheExceptionError,
    CacheKeyError,
    CacheSerializationError,
    cache_exception_handler,
)
from app.errors.circuit_breaker import CircuitBreakerError, circuit_breaker_exception_handler
from app.errors.email import (
    AuthenticationError,
    ConfigurationError,
    EmailServiceError,
    SendingError,
    email_client_exception_handler,
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
    "BASE_EXCEPTION",
    "email_client_exception_handler",
    "cache_exception_handler",
    "create_exception_handler",
    "BaseAppError",
    "CircuitBreakerError",
    "circuit_breaker_exception_handler",
]
