# tests/errors/test_circuitbreaker_error.py
"""Tests for app/errors/circuit_breaker.py module."""

from typing import cast
from unittest.mock import MagicMock

import pytest

from app.errors import CircuitBreakerError
from app.errors.base import create_exception_handler


class TestCircuitBreakerError:
    """Tests for CircuitBreakerError exception."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = CircuitBreakerError()
        assert error.detail == "Service temporarily unavailable"
        assert error.status_code == 503

    def test_custom_message(self) -> None:
        """Test custom error message."""
        error = CircuitBreakerError(detail="Custom error")
        assert error.detail == "Custom error"

    def test_retry_after(self) -> None:
        """Test retry_after attribute."""
        error = CircuitBreakerError(retry_after=30.0)
        assert error.retry_after == 30.0

    def test_circuit_name(self) -> None:
        """Test circuit_name attribute."""
        error = CircuitBreakerError(circuit_name="test_circuit")
        assert error.circuit_name == "test_circuit"

    def test_str_with_retry(self) -> None:
        """Test string representation with retry info."""
        error = CircuitBreakerError(detail="Error", retry_after=10.5)
        assert str(error) == "Error (retry in 10.5s)"

    def test_str_without_retry(self) -> None:
        """Test string representation without retry info."""
        error = CircuitBreakerError(detail="Error", retry_after=0.0)
        assert str(error) == "Error"

    @pytest.mark.asyncio
    async def test_exception_handler_response_json(self) -> None:
        """Test exception handler returns correct JSON response."""
        # Create mock request
        request = MagicMock()
        request.client.host = "127.0.0.1"
        request.url.path = "/test"
        logger = MagicMock()
        handler = create_exception_handler(logger)

        # Create error with custom message
        error = CircuitBreakerError(
            detail="Circuit is open",
            retry_after=30.0,
            circuit_name="test_circuit",
        )
        exc = cast(Exception, error)
        # Call the handler
        response = await handler(request, exc)

        # Assert response properties
        assert response.status_code == 503
        assert (
            response.body
            == b'{"detail":"Circuit is open","retry_after":30.0,"circuit_name":"test_circuit"}'
        )
        logger.warning.assert_called_once_with(
            "Circuit is open for ip: 127.0.0.1 for endpoint /test",
        )
