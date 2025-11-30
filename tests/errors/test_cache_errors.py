# tests/errors/test_cache_errors.py
"""Tests for app/errors/cache.py module."""

from unittest.mock import MagicMock

import pytest
from starlette import status

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


class TestCacheExceptionError:
    """Tests for CacheExceptionError base class."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = CacheExceptionError()
        assert error.msg == "Cache exception occurred"

    def test_custom_message(self) -> None:
        """Test custom error message."""
        error = CacheExceptionError("Custom cache error")
        assert error.msg == "Custom cache error"

    def test_status_code(self) -> None:
        """Test status code is 500."""
        error = CacheExceptionError()
        assert error.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_str_representation(self) -> None:
        """Test string representation."""
        error = CacheExceptionError("Test error")
        assert str(error) == "Test error"


class TestCacheKeyError:
    """Tests for CacheKeyError class."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = CacheKeyError()
        assert error.msg == "Cache key error"

    def test_custom_message(self) -> None:
        """Test custom error message."""
        error = CacheKeyError("Invalid key format")
        assert error.msg == "Invalid key format"

    def test_inherits_from_base(self) -> None:
        """Test inheritance from CacheExceptionError."""
        error = CacheKeyError()
        assert isinstance(error, CacheExceptionError)


class TestCacheSerializationError:
    """Tests for CacheSerializationError class."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = CacheSerializationError()
        assert error.msg == "Cannot serialize value"

    def test_custom_message(self) -> None:
        """Test custom error message."""
        error = CacheSerializationError("Failed to serialize object")
        assert error.msg == "Failed to serialize object"


class TestCacheDeserializationError:
    """Tests for CacheDeserializationError class."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = CacheDeserializationError()
        assert error.msg == "Cannot deserialize value"

    def test_custom_message(self) -> None:
        """Test custom error message."""
        error = CacheDeserializationError("Invalid JSON format")
        assert error.msg == "Invalid JSON format"


class TestCacheCompressionError:
    """Tests for CacheCompressionError class."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = CacheCompressionError()
        assert error.msg == "Cannot compress data"

    def test_status_code(self) -> None:
        """Test status code."""
        error = CacheCompressionError()
        assert error.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestCacheDecompressionError:
    """Tests for CacheDecompressionError class."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = CacheDecompressionError()
        assert error.msg == "Cannot decompress data"


class TestRateLimitError:
    """Tests for RateLimitError class."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = RateLimitError()
        assert error.msg == "Rate limit exceeded"

    def test_status_code_is_429(self) -> None:
        """Test status code is 429 Too Many Requests."""
        error = RateLimitError()
        assert error.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_custom_message(self) -> None:
        """Test custom error message."""
        error = RateLimitError("API rate limit exceeded")
        assert error.msg == "API rate limit exceeded"


class TestCacheExceptionHandler:
    """Tests for cache_exception_handler function."""

    @pytest.mark.asyncio
    async def test_handler_returns_orjson_response(self) -> None:
        """Test that handler returns ORJSONResponse."""
        request = MagicMock()
        request.client.host = "192.168.1.1"
        request.url.path = "/api/cache"

        exc = CacheExceptionError("Test error")

        response = await cache_exception_handler(request, exc)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @pytest.mark.asyncio
    async def test_handler_with_none_client(self) -> None:
        """Test handler when client is None."""
        request = MagicMock()
        request.client = None
        request.url.path = "/api/test"

        exc = CacheKeyError("Key not found")
        response = await cache_exception_handler(request, exc)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

