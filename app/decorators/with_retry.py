from collections.abc import Awaitable, Callable
from logging import getLogger
from typing import ParamSpec, TypeVar

from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.configs import file_logger

logger = file_logger(getLogger(__name__))

# Type variables for retry decorator
P = ParamSpec("P")
T = TypeVar("T")
# Retriable exception types
RETRIABLE_EXCEPTIONS = (RedisConnectionError, RedisTimeoutError, ConnectionError, TimeoutError)


def _log_before_sleep(
    max_retries: int,
) -> Callable[[RetryCallState], None]:
    """
    Create a before_sleep callback that logs retry attempts.

    Args:
        max_retries: Maximum number of retry attempts for log message.

    Returns:
        Callback function for tenacity before_sleep.
    """

    def before_sleep_callback(retry_state: RetryCallState) -> None:
        """Log retry information before sleeping."""
        exception = retry_state.outcome.exception() if retry_state.outcome else None
        # next_action contains the sleep duration
        sleep_duration = retry_state.next_action.sleep if retry_state.next_action else 0
        func_name = retry_state.fn.__name__ if retry_state.fn else "unknown"

        logger.warning(
            "Retry %d/%d for %s after %.2fs delay. Exception: %s",
            retry_state.attempt_number,
            max_retries,
            func_name,
            sleep_duration,
            exception,
        )

    return before_sleep_callback


def with_retry(
    max_retries: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    exec_retry: tuple[type[Exception], ...] = RETRIABLE_EXCEPTIONS,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """
    Apply retry logic with exponential backoff to async functions using Tenacity.

    Args:
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay between retries in seconds.
        max_delay: Maximum delay between retries in seconds.
        exec_retry: Tuple of exception types to retry on.

    Returns:
        Decorated function with retry logic.
    """
    return retry(
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=base_delay, min=base_delay, max=max_delay),
        retry=retry_if_exception_type(exec_retry),
        before_sleep=_log_before_sleep(max_retries),
        reraise=True,
    )
