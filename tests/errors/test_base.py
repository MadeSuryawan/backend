# tests/errors/test_base.py
"""Tests for app/errors/base.py module."""

from unittest.mock import MagicMock

import pytest
from fastapi.responses import ORJSONResponse

from app.errors import BaseAppError, create_exception_handler


class TestBaseAppError:
    """Tests for BaseAppError exception."""

    def test_default_values(self) -> None:
        """Test default initialization values."""
        error = BaseAppError()
        assert error.msg == "Internal Server Error"
        assert error.error_code == 500

    def test_custom_values(self) -> None:
        """Test custom initialization values."""
        error = BaseAppError(msg="Custom error", error_code=400)
        assert error.msg == "Custom error"
        assert error.error_code == 400

    def test_str_representation(self) -> None:
        """Test string representation returns message."""
        error = BaseAppError(msg="Test error")
        assert str(error) == "Test error"


class TestCreateExceptionHandler:
    """Tests for create_exception_handler factory function."""

    @pytest.mark.asyncio
    async def test_handler_with_base_app_error(self) -> None:
        """Test handler with BaseAppError exception."""
        logger = MagicMock()
        handler = create_exception_handler(logger)

        # Create mock request
        request = MagicMock()
        request.client.host = "192.168.1.1"
        request.url.path = "/api/test"

        # Create custom error
        error = BaseAppError(msg="Test error", error_code=400)

        # Call handler
        response = await handler(request, error)

        # Verify response
        assert response.status_code == 400
        assert response.body == b'{"detail":"Test error"}'

        # Verify logging
        logger.warning.assert_called_once_with(
            "Test error for ip: 192.168.1.1 for endpoint /api/test",
        )

    @pytest.mark.asyncio
    async def test_handler_with_generic_exception(self) -> None:
        """Test handler with generic Python exception."""
        logger = MagicMock()
        handler = create_exception_handler(logger)

        # Create mock request
        request = MagicMock()
        request.client.host = "127.0.0.1"
        request.url.path = "/api/error"

        # Create generic exception
        error = ValueError("Something went wrong")

        # Call handler
        response = await handler(request, error)

        # Verify default response
        assert response.status_code == 500
        assert response.body == b'{"detail":"Internal Server Error"}'

        # Verify logging
        logger.warning.assert_called_once_with(
            "Internal Server Error for ip: 127.0.0.1 for endpoint /api/error",
        )

    @pytest.mark.asyncio
    async def test_handler_with_no_client(self) -> None:
        """Test handler when request has no client."""
        logger = MagicMock()
        handler = create_exception_handler(logger)

        # Create mock request without client
        request = MagicMock()
        request.client = None
        request.url.path = "/api/test"

        # Create error
        error = BaseAppError(msg="Error")

        # Call handler
        _ = await handler(request, error)

        # Verify logging uses "unknown" as host
        logger.warning.assert_called_once_with("Error for ip: unknown for endpoint /api/test")

    @pytest.mark.asyncio
    async def test_handler_with_custom_exception_attributes(self) -> None:
        """Test handler extracts status_code and msg from custom exception."""

        class CustomError(Exception):
            def __init__(self) -> None:
                self.error_code = 418
                self.msg = "I'm a teapot"

        logger = MagicMock()
        handler = create_exception_handler(logger)

        # Create mock request
        request = MagicMock()
        request.client.host = "172.16.0.1"
        request.url.path = "/api/coffee"

        # Create custom error
        error = CustomError()

        # Call handler
        response = await handler(request, error)

        # Verify custom attributes are used
        assert response.status_code == 418
        assert response.body == b'{"detail":"I\'m a teapot"}'

        # Verify logging
        logger.warning.assert_called_once_with(
            "I'm a teapot for ip: 172.16.0.1 for endpoint /api/coffee",
        )

    @pytest.mark.asyncio
    async def test_handler_with_partial_custom_attributes(self) -> None:
        """Test handler with exception that has only status_code."""

        class PartialError(Exception):
            def __init__(self) -> None:
                self.msg = "Rate limit exceeded"
                self.error_code = 429

        logger = MagicMock()
        handler = create_exception_handler(logger)

        # Create mock request
        request = MagicMock()
        request.client.host = "8.8.8.8"
        request.url.path = "/api/rate-limited"

        # Create error with only status_code
        error = PartialError()

        # Call handler
        response = await handler(request, error)

        # Verify status_code is used but msg is default
        assert response.status_code == 429
        assert response.body == b'{"detail":"Rate limit exceeded"}'

    @pytest.mark.asyncio
    async def test_handler_returns_orjson_response(self) -> None:
        """Test handler returns ORJSONResponse instance."""

        logger = MagicMock()
        handler = create_exception_handler(logger)

        # Create mock request
        request = MagicMock()
        request.client.host = "localhost"
        request.url.path = "/test"

        # Create error
        error = BaseAppError()

        # Call handler
        response = await handler(request, error)

        # Verify response type
        assert isinstance(response, ORJSONResponse)
