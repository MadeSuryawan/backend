"""
Limiter Routes.

Endpoints to inspect limiter health and reset rate limits with clear error responses.
"""

from logging import getLogger

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import ORJSONResponse

from app.auth.permissions import AdminUserDep
from app.decorators.caching import get_cache_manager
from app.managers.rate_limiter import get_identifier
from app.schemas import LimiterHealthResponse, LimiterResetRequest, LimiterResetResponse
from app.utils.helpers import file_logger

logger = file_logger(getLogger(__name__))

router = APIRouter(prefix="/limiter", tags=["🚦 Limiter"])


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
    identifier = body.key or get_identifier(request)
    if not identifier:
        raise HTTPException(status_code=400, detail="Could not determine identifier")

    if body.all_endpoints:
        redis = get_cache_manager(request).redis_client
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
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"healthy": True, "storage": "redis", "detail": None},
                },
            },
        },
    },
    operation_id="limiter_status",
)
async def get_limiter_status(request: Request) -> ORJSONResponse:
    """
    Get status of the rate limiter storage.

    Parameters
    ----------
    request : Request
        Current request context.

    Returns
    -------
    ORJSONResponse
        Health status of limiter storage.
    """
    # Check if we can ping Redis via cache manager since it shares the same backend

    status = LimiterHealthResponse()

    redis_healthy = await get_cache_manager(request).redis_client.ping()
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
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "message": "Reset 3 rate limit keys for identifier '127.0.0.1'",
                        "count": 3,
                        "identifier": "127.0.0.1",
                    },
                },
            },
        },
        400: {
            "description": "Bad request",
            "content": {
                "application/json": {"example": {"detail": "Could not determine identifier"}},
            },
        },
        403: {
            "description": "Forbidden",
            "content": {
                "application/json": {
                    "example": {"detail": "Admin access required"},
                },
            },
        },
        503: {
            "description": "Redis unavailable",
            "content": {"application/json": {"example": {"detail": "Redis unavailable"}}},
        },
        501: {
            "description": "Not implemented",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Per-endpoint reset requires explicit endpoint knowledge. Use all_endpoints=True for now.",
                    },
                },
            },
        },
    },
    operation_id="limiter_reset",
)
async def reset_limiter(
    request: Request,
    body: LimiterResetRequest,
    admin_user: AdminUserDep,
) -> LimiterResetResponse:
    """
    Return limiter reset result.

    Parameters
    ----------
    request : Request
        Current request context.
    body : LimiterResetRequest
        Reset parameters.
    admin_user : UserDB
        Admin user (enforced by AdminUserDep dependency).

    Returns
    -------
    LimiterResetResponse
        Structured result including message, count, and identifier.
    """
    return await _perform_limiter_reset(request, body)
