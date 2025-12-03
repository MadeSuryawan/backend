from logging import getLogger

from starlette.status import HTTP_503_SERVICE_UNAVAILABLE

from app.configs import file_logger
from app.errors import BaseAppError, create_exception_handler

logger = file_logger(getLogger(__name__))


class CircuitBreakerError(BaseAppError):
    """
    Raised when circuit breaker is open and rejecting requests.

    Includes retry information for clients to implement backoff.
    """

    def __init__(
        self,
        detail: str = "Service temporarily unavailable",
        retry_after: float = 0.0,
        circuit_name: str = "unknown",
    ) -> None:
        """
        Initialize CircuitBreakerError.

        Args:
            detail: Error message describing the issue.
            retry_after: Seconds until the circuit may allow requests again.
            circuit_name: Name of the circuit breaker that triggered the error.
        """
        super().__init__(detail)
        self.detail = detail
        self.retry_after = retry_after
        self.circuit_name = circuit_name
        self.status_code = HTTP_503_SERVICE_UNAVAILABLE

    def __str__(self) -> str:
        """Return string representation with retry information."""
        if self.retry_after > 0:
            return f"{self.detail} (retry in {self.retry_after:.1f}s)"
        return self.detail


circuit_breaker_exception_handler = create_exception_handler(logger)
