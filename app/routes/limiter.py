from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import ORJSONResponse
from slowapi.extension import Limiter
from starlette.status import HTTP_403_FORBIDDEN

from app.configs import file_logger
from app.errors.base import host
from app.managers import cache_manager
from app.managers.rate_limiter import get_identifier
from app.schemas import LimiterHealthResponse, LimiterResetRequest, LimiterResetResponse

logger = file_logger(getLogger(__name__))

router = APIRouter(prefix="/limiter", tags=["limiter"])


def get_limiter(app: FastAPI) -> Limiter:
    """Get limiter instance."""
    return app.state.limiter


LimiterDep = Annotated[Limiter, Depends(get_limiter)]


async def _perform_limiter_reset(
    request: Request,
    body: LimiterResetRequest,
) -> LimiterResetResponse:
    """
    Execute limiter reset operations and return structured result.

    Separates business logic (authorization, identifier resolution, Redis scanning)
    from response generation for improved testability.

    Args:
        request: Incoming FastAPI request.
        body: Parameters controlling reset behavior.

    Returns:
        LimiterResetResponse with message, count, and identifier.

    Raises:
        HTTPException: For authorization failures, invalid input, or unavailable backends.
    """

    if (client_host := host(request)) not in ("127.0.0.1", "::1", "localhost"):
        logger.warning(f"Unauthorized access attempt to limiter reset from {client_host}")
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Admin access required (localhost only)",
        )

    identifier = body.key or get_identifier(request)
    if not identifier:
        raise HTTPException(status_code=400, detail="Could not determine identifier")

    if body.all_endpoints:
        redis = cache_manager.redis_client
        if not await redis.ping():
            raise HTTPException(status_code=503, detail="Redis unavailable")

        count = 0
        pattern = f"*{identifier}*"
        async for key in redis.scan_iter(pattern):
            if await redis.delete(key):
                count += 1

        message = f"Reset {count} rate limit keys for identifier '{identifier}'"
        return LimiterResetResponse(message=message, count=count, identifier=identifier)

    raise HTTPException(
        status_code=501,
        detail="Per-endpoint reset requires explicit endpoint knowledge. Use all_endpoints=True for now.",
    )


@router.get(
    "/status",
    summary="Get limiter status",
    response_class=ORJSONResponse,
    response_model=LimiterHealthResponse,
)
async def get_limiter_status(request: Request) -> ORJSONResponse:
    """Get status of the rate limiter storage."""
    # Check if we can ping Redis via cache manager since it shares the same backend

    status = LimiterHealthResponse()

    redis_healthy = await cache_manager.redis_client.ping()
    if not redis_healthy:
        status.detail = "Falling back to in-memory storage or disconnected"
        status.storage = "in-memory"
        status.healthy = False

    return ORJSONResponse(status.model_dump())


@router.post(
    "/reset",
    summary="Reset rate limits",
    response_class=ORJSONResponse,
    response_model=LimiterResetResponse,
)
async def reset_limiter(
    request: Request,
    body: LimiterResetRequest,
) -> LimiterResetResponse:
    """
    Return limiter reset result.

    Delegates all business logic to a dedicated helper for separation of concerns.

    Args:
        request: FastAPI Request object.
        body: Reset parameters.
    """
    return await _perform_limiter_reset(request, body)
