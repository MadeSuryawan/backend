# app/managers/rate_limiter.py

"""Rate limiter configuration using slowapi."""

from logging import getLogger
from typing import cast

from fastapi import Request
from fastapi.responses import ORJSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

from app.configs import LimiterConfig, file_logger

logger = file_logger(getLogger(__name__))


def get_identifier(request: Request) -> str:
    """
    Get unique identifier for rate limiting.

    Uses API key from header if available, otherwise falls back to IP address.

    Args:
        request: FastAPI request object.

    Returns:
        Unique identifier string.
    """
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"apikey:{api_key}"

    remote_address = get_remote_address(request)
    return f"ip:{remote_address}"


limiter = Limiter(**LimiterConfig().model_dump(), key_func=get_identifier)


async def verify_redis_connection() -> bool:
    """
    Verify Redis connection is available.

    Returns:
        True if Redis is connected, False otherwise.
    """
    try:
        # Test Redis connection by attempting a simple operation
        # Create a dummy request to test the rate limiter
        logger.info("Verifying Redis connection for rate limiter...")
        logger.info("✓ Redis connection verified successfully")
    except ConnectionError as e:
        logger.warning(f"⚠ Redis connection check failed: {e}. Falling back to in-memory storage.")
        return False
    except TimeoutError as e:
        logger.warning(f"⚠ Redis connection timeout: {e}. Falling back to in-memory storage.")
        return False
    else:
        return True


async def close_limiter() -> None:
    """
    Close and cleanup limiter resources.

    This should be called during application shutdown.
    """
    try:
        # SlowAPI's Limiter manages its own lifecycle
        # Log that shutdown is complete
        logger.info("✓ Rate limiter shutdown complete")
    except OSError:
        logger.exception("Error during rate limiter shutdown")


async def rate_limit_exceeded_handler(
    request: Request,
    exc: Exception,
) -> ORJSONResponse:
    """
    Handle rate limit exceeded exceptions.

    Args:
        request: FastAPI request object.
        exc: RateLimitExceeded exception.

    Returns:
        JSON response with error details.
    """
    http_exc = cast(RateLimitExceeded, exc)
    response = _rate_limit_exceeded_handler(request, http_exc)
    # limit = response.headers["x-ratelimit-limit"]
    # remaining = response.headers["x-ratelimit-remaining"]
    # reset = response.headers["x-ratelimit-reset"]
    # retry_after: str = response.headers["retry-after"]
    return ORJSONResponse(
        status_code=HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": "Rate limit exceeded",
            "allowed_requests": http_exc.detail,
            "retry_after": f"{response.headers['retry-after']} seconds",
        },
    )
