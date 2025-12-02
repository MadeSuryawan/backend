# tests/errors/test_circuitbreaker_error.py
"""Tests for app/errors/circuit_breaker.py module."""

from unittest.mock import MagicMock

import pytest

from app.errors import CircuitBreakerError, circuit_breaker_exception_handler


class TestCircuitBreakerError:
    """Tests for CircuitBreakerError exception."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = CircuitBreakerError()
        assert error.msg == "Service temporarily unavailable"
        assert error.error_code == 503

    def test_custom_message(self) -> None:
        """Test custom error message."""
        error = CircuitBreakerError(msg="Custom error")
        assert error.msg == "Custom error"

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
        error = CircuitBreakerError(msg="Error", retry_after=10.5)
        assert str(error) == "Error (retry in 10.5s)"

    def test_str_without_retry(self) -> None:
        """Test string representation without retry info."""
        error = CircuitBreakerError(msg="Error", retry_after=0.0)
        assert str(error) == "Error"

    @pytest.mark.asyncio
    async def test_exception_handler_response_json(self) -> None:
        """Test exception handler returns correct JSON response."""
        # Create mock request
        request = MagicMock()
        request.client.host = "127.0.0.1"
        request.url.path = "/test"

        # Create error with custom message
        error = CircuitBreakerError(
            msg="Circuit is open",
            retry_after=30.0,
            circuit_name="test_circuit",
        )

        # Call the handler
        response = await circuit_breaker_exception_handler(request, error)

        # Assert response properties
        assert response.status_code == 503
        assert (
            response.body
            == b'{"detail":"Circuit is open","retry_after":30.0,"circuit_name":"test_circuit"}'
        )
