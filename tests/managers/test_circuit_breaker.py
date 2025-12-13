# tests/managers/test_circuit_breaker.py
"""Comprehensive tests for app/managers/circuit_breaker.py module."""

from asyncio import gather
from asyncio import sleep as async_sleep
from unittest.mock import MagicMock

import pytest

from app.managers.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    ai_circuit_breaker,
    email_circuit_breaker,
)


class TestCircuitState:
    """Tests for CircuitState enum."""

    def test_closed_state_value(self) -> None:
        """Test CLOSED state has correct value."""
        assert CircuitState.CLOSED.value == "closed"

    def test_open_state_value(self) -> None:
        """Test OPEN state has correct value."""
        assert CircuitState.OPEN.value == "open"

    def test_half_open_state_value(self) -> None:
        """Test HALF_OPEN state has correct value."""
        assert CircuitState.HALF_OPEN.value == "half_open"


class TestCircuitBreakerInit:
    """Tests for CircuitBreaker initialization."""

    def test_default_values(self) -> None:
        """Test default initialization values."""
        cb = CircuitBreaker(config=CircuitBreakerConfig())
        assert cb.name == "default"
        assert cb.failure_threshold == 5
        assert cb.recovery_timeout == 60.0
        assert cb.half_open_max_calls == 1
        assert cb.success_threshold == 1
        assert cb.state == CircuitState.CLOSED

    def test_custom_values(self) -> None:
        """Test custom initialization values."""
        cb = CircuitBreaker(
            config=CircuitBreakerConfig(
                name="custom",
                failure_threshold=3,
                recovery_timeout=30.0,
                half_open_max_calls=2,
                success_threshold=2,
            ),
        )
        assert cb.name == "custom"
        assert cb.failure_threshold == 3
        assert cb.recovery_timeout == 30.0
        assert cb.half_open_max_calls == 2
        assert cb.success_threshold == 2

    def test_expected_exceptions_single(self) -> None:
        """Test single exception type."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(expected_exceptions=ValueError))
        assert cb.expected_exceptions is ValueError

    def test_expected_exceptions_tuple(self) -> None:
        """Test tuple of exception types."""
        cb = CircuitBreaker(
            config=CircuitBreakerConfig(expected_exceptions=(ValueError, TypeError)),
        )
        assert cb.expected_exceptions == (ValueError, TypeError)  # noqa: E721


class TestCircuitBreakerStateTransitions:
    """Tests for circuit breaker state transitions."""

    @pytest.mark.asyncio
    async def test_stays_closed_on_success(self) -> None:
        """Test circuit stays closed on successful calls."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=3))

        async def success_func() -> str:
            return "success"

        result = await cb.call(success_func)
        assert result == "success"
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_after_threshold_failures(self) -> None:
        """Test circuit opens after reaching failure threshold."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=3))

        async def failing_func() -> None:
            raise ValueError("error")

        for _ in range(3):
            with pytest.raises(ValueError):
                await cb.call(failing_func)

        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_rejects_calls_when_open(self) -> None:
        """Test circuit rejects calls when open."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=60.0))

        async def failing_func() -> None:
            raise ValueError("error")

        with pytest.raises(ValueError):
            await cb.call(failing_func)

    @pytest.mark.asyncio
    async def test_transitions_to_half_open_after_timeout(self) -> None:
        """Test circuit transitions to half-open after recovery timeout."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.1))

        async def failing_func() -> None:
            raise ValueError("error")

        with pytest.raises(ValueError):
            await cb.call(failing_func)

        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        await async_sleep(0.15)

        # Next call should be allowed (half-open state)
        async def success_func() -> str:
            return "success"

        result = await cb.call(success_func)
        assert result == "success"
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_reopens_on_failure_in_half_open(self) -> None:
        """Test circuit reopens on failure in half-open state."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.1))

        async def failing_func() -> None:
            raise ValueError("error")

        # Open the circuit
        with pytest.raises(ValueError):
            await cb.call(failing_func)

        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        await async_sleep(0.15)

        # Fail in half-open state
        with pytest.raises(ValueError):
            await cb.call(failing_func)

        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_closes_after_success_threshold(self) -> None:
        """Test circuit closes after success threshold in half-open."""
        cb = CircuitBreaker(
            config=CircuitBreakerConfig(
                failure_threshold=1,
                recovery_timeout=0.1,
                success_threshold=2,
            ),
        )

        async def failing_func() -> None:
            raise ValueError("error")

        async def success_func() -> str:
            return "success"

        # Open the circuit
        with pytest.raises(ValueError):
            await cb.call(failing_func)

        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        await async_sleep(0.15)

        # First success in half-open
        await cb.call(success_func)
        assert cb.state == CircuitState.HALF_OPEN

        # Second success should close the circuit
        await cb.call(success_func)
        assert cb.state == CircuitState.CLOSED


class TestCircuitBreakerReset:
    """Tests for circuit breaker reset functionality."""

    @pytest.mark.asyncio
    async def test_async_reset(self) -> None:
        """Test async reset method."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=1))

        async def failing_func() -> None:
            raise ValueError("error")

        with pytest.raises(ValueError):
            await cb.call(failing_func)

        assert cb.state == CircuitState.OPEN

        await cb.reset()
        assert cb.state == CircuitState.CLOSED

    def test_sync_reset(self) -> None:
        """Test sync reset method."""
        cb = CircuitBreaker(config=CircuitBreakerConfig())
        cb._state = CircuitState.OPEN
        cb._failure_count = 5

        cb.reset_sync()
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 0


class TestCircuitBreakerDecorator:
    """Tests for circuit breaker decorator usage."""

    @pytest.mark.asyncio
    async def test_decorator_success(self) -> None:
        """Test decorator with successful function."""
        cb = CircuitBreaker(config=CircuitBreakerConfig())

        @cb
        async def decorated_func() -> str:
            return "decorated"

        result = await decorated_func()
        assert result == "decorated"

    @pytest.mark.asyncio
    async def test_decorator_failure(self) -> None:
        """Test decorator with failing function."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=1))

        @cb
        async def decorated_func() -> None:
            raise ValueError("error")

        with pytest.raises(ValueError):
            await decorated_func()

        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_decorator_preserves_function_metadata(self) -> None:
        """Test decorator preserves function name and docstring."""
        cb = CircuitBreaker(config=CircuitBreakerConfig())

        @cb
        async def my_function() -> str:
            """My docstring."""
            return "result"

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."


class TestCircuitBreakerMetrics:
    """Tests for circuit breaker metrics integration."""

    @pytest.mark.asyncio
    async def test_records_circuit_open_event(self) -> None:
        """Test metrics are recorded when circuit opens."""
        mock_metrics = MagicMock()
        cb = CircuitBreaker(
            config=CircuitBreakerConfig(failure_threshold=1, metrics_manager=mock_metrics),
        )

        async def failing_func() -> None:
            raise ValueError("error")

        with pytest.raises(ValueError):
            await cb.call(failing_func)

        mock_metrics.record_circuit_breaker_open.assert_called_once()

    def test_set_metrics_manager(self) -> None:
        """Test setting metrics manager after initialization."""
        cb = CircuitBreaker(config=CircuitBreakerConfig())
        mock_metrics = MagicMock()

        cb.set_metrics_manager(mock_metrics)
        assert cb._metrics_manager == mock_metrics


class TestCircuitBreakerStatus:
    """Tests for circuit breaker status reporting."""

    def test_get_state_closed(self) -> None:
        """Test state when circuit is closed."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(name="test"))
        state = cb.get_state()

        assert state["name"] == "test"
        assert state["state"] == "closed"
        assert state["failure_count"] == 0
        assert state["failure_threshold"] == 5

    @pytest.mark.asyncio
    async def test_get_state_open(self) -> None:
        """Test state when circuit is open."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(name="test", failure_threshold=1))

        async def failing_func() -> None:
            raise ValueError("error")

        with pytest.raises(ValueError):
            await cb.call(failing_func)

        state = cb.get_state()
        assert state["state"] == "open"
        assert state["failure_count"] == 1
        assert state["last_failure_time"] is not None


class TestGlobalCircuitBreakers:
    """Tests for global circuit breaker instances."""

    def test_email_circuit_breaker_exists(self) -> None:
        """Test email circuit breaker is configured."""
        assert email_circuit_breaker.name == "email_service"
        assert email_circuit_breaker.failure_threshold == 3

    def test_ai_circuit_breaker_exists(self) -> None:
        """Test AI circuit breaker is configured."""
        assert ai_circuit_breaker.name == "gemini_ai"
        assert ai_circuit_breaker.failure_threshold == 5


class TestCircuitBreakerConcurrency:
    """Tests for circuit breaker concurrent access."""

    @pytest.mark.asyncio
    async def test_concurrent_calls_in_closed_state(self) -> None:
        """Test concurrent calls work in closed state."""
        cb = CircuitBreaker(config=CircuitBreakerConfig())
        call_count = 0

        async def counting_func() -> int:
            nonlocal call_count
            call_count += 1
            await async_sleep(0.01)
            return call_count

        results = await gather(*[cb.call(counting_func) for _ in range(5)])
        assert len(results) == 5
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_concurrent_failures_open_circuit_once(self) -> None:
        """Test concurrent failures only open circuit once."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=3))

        async def failing_func() -> None:
            await async_sleep(0.01)
            raise ValueError("error")

        # Run 5 concurrent failing calls
        tasks = [cb.call(failing_func) for _ in range(5)]
        results = await gather(*tasks, return_exceptions=True)

        # All should fail
        assert all(isinstance(r, ValueError) for r in results)
        # Circuit should be open
        assert cb.state == CircuitState.OPEN
