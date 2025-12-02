# app/managers/circuit_breaker.py
"""
Circuit breaker pattern implementation for external service calls.

This module provides circuit breaker functionality to prevent cascading failures
when external services (like email or AI APIs) are experiencing issues.

Features:
    - Async-safe with asyncio.Lock for thread safety
    - Configurable failure thresholds and recovery timeouts
    - Half-open state with success threshold for gradual recovery
    - Metrics integration for monitoring circuit breaker state
    - Decorator support for easy integration
"""

from asyncio import Lock
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from logging import getLogger
from time import time
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, cast

from app.configs import file_logger
from app.errors import CircuitBreakerError, EmailServiceError

if TYPE_CHECKING:
    from app.managers.metrics import MetricsManager

logger = file_logger(getLogger(__name__))

# Type variables for generic decorator support
P = ParamSpec("P")
T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, requests pass through
    OPEN = "open"  # Failing, reject requests immediately
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for CircuitBreaker."""

    name: str = "default"
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    expected_exceptions: type[Exception] | tuple[type[Exception], ...] = Exception
    half_open_max_calls: int = 1
    success_threshold: int = 1
    metrics_manager: "MetricsManager | None" = None


class CircuitBreaker:
    """
    Circuit breaker for external service calls with async support.

    Implements the circuit breaker pattern to prevent cascading failures
    when external services are unavailable. Uses asyncio.Lock for thread-safe
    state management in async contexts.

    States:
        - CLOSED: Normal operation, all requests pass through
        - OPEN: Service is failing, requests are rejected immediately
        - HALF_OPEN: Testing recovery, limited requests allowed

    Attributes:
        name: Identifier for this circuit breaker (used in logs and metrics)
        failure_threshold: Number of failures before opening the circuit
        recovery_timeout: Seconds to wait before attempting recovery
        half_open_max_calls: Max concurrent calls in HALF_OPEN state
        success_threshold: Successes needed in HALF_OPEN to close circuit
    """

    __slots__ = (
        "_failure_count",
        "_half_open_successes",
        "_last_failure_time",
        "_lock",
        "_metrics_manager",
        "_state",
        "expected_exceptions",
        "failure_threshold",
        "half_open_max_calls",
        "name",
        "recovery_timeout",
        "success_threshold",
    )

    def __init__(
        self,
        config: CircuitBreakerConfig,
    ) -> None:
        """
        Initialize circuit breaker.

        Args:
            config: Configuration object for the circuit breaker.
        """
        self.name = config.name
        self.failure_threshold = config.failure_threshold
        self.recovery_timeout = config.recovery_timeout
        self.expected_exceptions = config.expected_exceptions
        self.half_open_max_calls = config.half_open_max_calls
        self.success_threshold = config.success_threshold
        self._metrics_manager = config.metrics_manager

        # Internal state (protected by async lock)
        self._failure_count: int = 0
        self._half_open_successes: int = 0
        self._last_failure_time: float | None = None
        self._state: CircuitState = CircuitState.CLOSED
        self._lock: Lock = Lock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state (read-only)."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Get current failure count (read-only)."""
        return self._failure_count

    @property
    def last_failure_time(self) -> float | None:
        """Get timestamp of last failure (read-only)."""
        return self._last_failure_time

    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> T:
        """
        Execute async function with circuit breaker protection.

        Args:
            func: Async function to execute.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.

        Returns:
            Result from the function call.

        Raises:
            CircuitBreakerError: If circuit is OPEN and not ready for recovery.
            Exception: Original exception if the function fails.
        """
        exc = cast(type[Exception], self.expected_exceptions)
        async with self._lock:
            await self._check_state()

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except exc:
            await self._on_failure()
            raise

    async def _check_state(self) -> None:
        """
        Check circuit state and transition if necessary.

        Raises:
            CircuitBreakerError: If circuit is OPEN and not ready for recovery.
        """
        if self._state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._state = CircuitState.HALF_OPEN
                self._half_open_successes = 0
                logger.info(f"Circuit breaker '{self.name}' entering HALF_OPEN state")
            else:
                retry_after = self._time_until_reset()
                logger.warning(
                    f"Circuit breaker '{self.name}' is OPEN. Retry in {retry_after:.1f}s",
                )
                raise CircuitBreakerError(
                    msg=f"Service '{self.name}' temporarily unavailable",
                    retry_after=retry_after,
                    circuit_name=self.name,
                )

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if self._last_failure_time is None:
            return True
        return time() - self._last_failure_time >= self.recovery_timeout

    def _time_until_reset(self) -> float:
        """Calculate seconds remaining until recovery attempt."""
        if self._last_failure_time is None:
            return 0.0
        elapsed = time() - self._last_failure_time
        return max(0.0, self.recovery_timeout - elapsed)

    async def _on_success(self) -> None:
        """Handle successful call - potentially close the circuit."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._half_open_successes = 0
                    logger.info(f"Circuit breaker '{self.name}' recovered, now CLOSED")
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success in CLOSED state
                self._failure_count = 0

    async def _on_failure(self) -> None:
        """Handle failed call - potentially open the circuit."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in HALF_OPEN reopens the circuit
                self._state = CircuitState.OPEN
                self._half_open_successes = 0
                logger.warning(
                    f"Circuit breaker '{self.name}' reopened after failure in HALF_OPEN",
                )
                self._record_circuit_open()
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.error(
                    f"Circuit breaker '{self.name}' OPENED after "
                    f"{self._failure_count} consecutive failures",
                )
                self._record_circuit_open()

    def _record_circuit_open(self) -> None:
        """Record circuit open event to metrics if available."""
        if self._metrics_manager is not None:
            self._metrics_manager.record_circuit_breaker_open()

    def set_metrics_manager(self, metrics_manager: "MetricsManager") -> None:
        """
        Set the metrics manager for recording circuit breaker events.

        Args:
            metrics_manager: MetricsManager instance for recording events.
        """
        self._metrics_manager = metrics_manager

    async def reset(self) -> None:
        """Manually reset circuit breaker to CLOSED state."""
        async with self._lock:
            self._failure_count = 0
            self._half_open_successes = 0
            self._last_failure_time = None
            self._state = CircuitState.CLOSED
        logger.info(f"Circuit breaker '{self.name}' manually reset")

    def reset_sync(self) -> None:
        """
        Reset circuit breaker synchronously to CLOSED state.

        Note: This is not thread-safe with async operations.
        Use only for testing or initialization.
        """
        self._failure_count = 0
        self._half_open_successes = 0
        self._last_failure_time = None
        self._state = CircuitState.CLOSED
        logger.info(f"Circuit breaker '{self.name}' manually reset (sync)")

    def get_state(self) -> dict[str, Any]:
        """
        Get current circuit breaker state as a dictionary.

        Returns:
            Dictionary containing:
                - name: Circuit breaker name
                - state: Current state (closed/open/half_open)
                - failure_count: Current consecutive failure count
                - failure_threshold: Threshold for opening circuit
                - last_failure_time: Timestamp of last failure
                - time_until_reset: Seconds until recovery attempt (if OPEN)
                - success_threshold: Required successes to close from HALF_OPEN
                - half_open_successes: Current success count in HALF_OPEN
        """
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "last_failure_time": self._last_failure_time,
            "time_until_reset": (
                self._time_until_reset() if self._state == CircuitState.OPEN else 0.0
            ),
            "success_threshold": self.success_threshold,
            "half_open_successes": self._half_open_successes,
        }

    def __call__(
        self,
        func: Callable[P, Awaitable[T]],
    ) -> Callable[P, Awaitable[T]]:
        """
        Wrap an async function with circuit breaker protection as a decorator.

        Usage:
            @circuit_breaker
            async def my_function():
                ...

        Args:
            func: Async function to wrap.

        Returns:
            Wrapped function with circuit breaker protection.
        """

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return await self.call(func, *args, **kwargs)

        return wrapper


# Global circuit breakers for different services
ai_circuit_breaker = CircuitBreaker(
    config=CircuitBreakerConfig(
        name="gemini_ai",
        failure_threshold=5,
        recovery_timeout=60.0,
        expected_exceptions=Exception,
    ),
)

email_circuit_breaker = CircuitBreaker(
    config=CircuitBreakerConfig(
        name="email_service",
        failure_threshold=3,
        recovery_timeout=30.0,
        expected_exceptions=EmailServiceError,
    ),
)
