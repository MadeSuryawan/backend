# app/routes/health.py
"""
Health and System Routes.

Provides Kubernetes-compatible health endpoints, legacy health checks,
metrics, and utility endpoints for the BaliBlissed Backend.

Endpoints
---------
- /health/live : Liveness probe for Kubernetes
- /health/ready : Readiness probe for Kubernetes
- /health : Legacy health check with comprehensive status
- /favicon.ico : Serve favicon
- /metrics/legacy : Legacy metrics format
- / : Root welcome endpoint

Rate Limiting
-------------
All endpoints include explicit rate limits and 429 responses.
Health probes (/health/live, /health/ready) are exempt from rate limiting.
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, ORJSONResponse, Response

from app.configs import settings
from app.decorators.caching import get_cache_manager
from app.dependencies import EmailDep, HealthCheckerDep
from app.errors import EmailServiceError
from app.managers.circuit_breaker import ai_circuit_breaker, email_circuit_breaker
from app.managers.metrics import get_system_metrics, metrics_manager
from app.managers.rate_limiter import limiter
from app.schemas.cache import CacheHealthResponse, CircuitBreakerStatus, ServicesStatus
from app.utils.helpers import today_str

router = APIRouter(tags=["🩺 Health"])


# --- Liveness Probe ---
@router.get(
    "/health/live",
    tags=["🩺 Health"],
    summary="Liveness probe",
    response_model=dict,
    response_class=ORJSONResponse,
    include_in_schema=settings.DOCS_ENABLED,
    operation_id="liveness_probe",
)
@limiter.exempt
async def liveness_probe(
    request: Request,
    health_checker: HealthCheckerDep,
) -> ORJSONResponse:
    """
    Kubernetes liveness probe endpoint.

    This endpoint performs a basic check that the application is running.
    It does NOT check external dependencies. If this fails, Kubernetes
    will restart the pod.

    Parameters
    ----------
    request : Request
        Current request context.
    health_checker : HealthCheckerDep
        Health checker dependency.

    Returns
    -------
    ORJSONResponse
        Liveness status (always 200 if app is responsive).

    Examples
    --------
    Request
        GET /health/live
    Response
        200 OK
        {"status": "live", "timestamp": "2025-01-01T12:00:00Z"}
    """
    status = health_checker.check_liveness()
    return ORJSONResponse(
        content=status.to_dict(),
        status_code=200,
    )


# --- Readiness Probe ---
@router.get(
    "/health/ready",
    tags=["🩺 Health"],
    summary="Readiness probe",
    response_model=dict,
    response_class=ORJSONResponse,
    include_in_schema=settings.DOCS_ENABLED,
    responses={
        200: {
            "description": "Service is ready to accept traffic",
            "content": {
                "application/json": {
                    "example": {
                        "status": "ready",
                        "timestamp": "2025-01-01T12:00:00Z",
                        "version": "1.0.0",
                        "checks": {
                            "database": {"status": "pass", "response_ms": 15},
                            "redis": {"status": "pass", "response_ms": 5},
                            "disk": {"status": "pass", "usage_percent": 45},
                        },
                    },
                },
            },
        },
        503: {
            "description": "Service is not ready",
            "content": {
                "application/json": {
                    "example": {
                        "status": "not_ready",
                        "timestamp": "2025-01-01T12:00:00Z",
                        "version": "1.0.0",
                        "checks": {
                            "database": {
                                "status": "fail",
                                "response_ms": 2000,
                                "message": "Connection timeout",
                            },
                        },
                    },
                },
            },
        },
    },
    operation_id="readiness_probe",
)
@limiter.exempt
async def readiness_probe(request: Request, health_checker: HealthCheckerDep) -> ORJSONResponse:
    """
    Kubernetes readiness probe endpoint.

    This endpoint checks all external dependencies (database, Redis).
    If this fails, Kubernetes stops routing traffic to the pod.

    Parameters
    ----------
    request : Request
        Current request context.
    health_checker : HealthCheckerDep
        Health checker dependency.

    Returns
    -------
    ORJSONResponse
        Readiness status with component checks.

    Examples
    --------
    Request
        GET /health/ready
    Response
        200 OK
        {"status": "ready", "timestamp": "2025-01-01T12:00:00Z", "checks": {...}}
    """
    status = await health_checker.check_readiness()
    status_code = 200 if status.is_healthy else 503
    return ORJSONResponse(
        content=status.to_dict(),
        status_code=status_code,
    )


# --- Legacy Health Check (Conditional) ---
health_check_router = APIRouter()


@health_check_router.get(
    settings.HEALTH_CHECK_ENDPOINT,
    tags=["🩺 Health"],
    summary="Health check endpoint (legacy)",
    response_model=dict,
    response_class=ORJSONResponse,
    include_in_schema=settings.DOCS_ENABLED,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "version": "1.0.0",
                        "status": "ready",
                        "timestamp": "2025-01-01T12:00:00Z",
                        "checks": {
                            "database": {"status": "pass", "response_ms": 15},
                            "redis": {"status": "pass", "response_ms": 5},
                            "disk": {"status": "pass", "usage_percent": 45},
                        },
                    },
                },
            },
        },
    },
    operation_id="health_check",
)
@limiter.exempt
async def health_check(
    request: Request,
    email_client: EmailDep,
    health_checker: HealthCheckerDep,
) -> ORJSONResponse:
    """
    Health check endpoint with comprehensive status (legacy format).

    This endpoint is kept for backward compatibility. New deployments
    should use /health/live and /health/ready instead.

    Parameters
    ----------
    request : Request
        Current request context.
    email_client : EmailDep
        Email client dependency.
    health_checker : HealthCheckerDep
        Health checker dependency.

    Returns
    -------
    ORJSONResponse
        Health status including services and cache information.

    Examples
    --------
    Request
        GET /health
    Response
        200 OK
        {"version": "1.0.0", "status": "ready", ...}
    """

    # Get cache health info
    cache_health_data = await get_cache_manager(request).health_check()

    # Determine AI client status
    ai_client_status = (
        "initialized"
        if hasattr(request.app.state, "ai_client") and request.app.state.ai_client
        else "not_initialized"
    )

    # Determine Email client status
    try:
        email_client_status = "available" if email_client.service else "not_configured"
    except EmailServiceError:
        email_client_status = "not_configured"

    # Get readiness status
    readiness = await health_checker.check_readiness()

    # Build services status
    services = ServicesStatus(
        ai_client=ai_client_status,
        email_client=email_client_status,
        ai_circuit_breaker=CircuitBreakerStatus(**ai_circuit_breaker.get_state()),
        email_circuit_breaker=CircuitBreakerStatus(**email_circuit_breaker.get_state()),
    )

    # Build response combining new and legacy formats
    response_data = {
        "version": request.app.version,
        "status": readiness.status.value,
        "timestamp": today_str(),
        "services": services.model_dump(),
        "cache": CacheHealthResponse(**cache_health_data).model_dump(),
        "checks": readiness.to_dict().get("checks", {}),
    }

    return ORJSONResponse(response_data)


# Conditionally include health_check_router based on settings
if settings.HEALTH_CHECK_ENABLED:
    router.include_router(health_check_router)


# --- Favicon ---
@router.get("/favicon.ico", tags=["🖼️ Assets"], include_in_schema=False)
async def get_favicon() -> FileResponse:
    """
    Get favicon.

    Returns
    -------
    FileResponse
        Favicon file from the app directory.
    """
    favicon_path = Path(__file__).parent.parent / "favicon.ico"
    return FileResponse(favicon_path)


# --- Legacy Metrics ---
@router.get(
    "/metrics/legacy",
    tags=["📈 Metrics"],
    response_class=ORJSONResponse,
    summary="Get legacy metrics format",
    description="Get API performance metrics in legacy JSON format.",
    include_in_schema=settings.DOCS_ENABLED,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "timestamp": "2025-01-01",
                        "api_metrics": {"requests": 100, "latency_ms_avg": 12.3},
                        "system_metrics": {"cpu": 0.42, "mem": 0.58},
                    },
                },
            },
        },
    },
    operation_id="get_metrics_legacy",
)
@limiter.limit("5/minute")
async def get_metrics_legacy(request: Request, response: Response) -> ORJSONResponse:
    """
    Get API performance metrics in legacy format.

    This endpoint is kept for backward compatibility.
    The new /metrics endpoint provides Prometheus format.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Current response context.

    Returns
    -------
    ORJSONResponse
        Dictionary containing performance metrics.

    Notes
    -----
    Rate limited to 5 requests per minute.

    Examples
    --------
    Request
        GET /metrics/legacy
    Response
        200 OK
        {"timestamp": "2025-01-01", "api_metrics": {...}, "system_metrics": {...}}
    """
    api_metrics = metrics_manager.get_metrics()
    system_metrics = await get_system_metrics()

    return ORJSONResponse(
        content={
            "timestamp": today_str(),
            "api_metrics": api_metrics,
            "system_metrics": system_metrics,
        },
    )


# --- Root Endpoint ---
@router.get(
    "/",
    tags=["🏠 Root"],
    summary="Root access",
    response_model=dict[str, str],
    response_class=JSONResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"message": "Welcome to BaliBlissed Backend"},
                },
            },
        },
    },
    operation_id="root_access",
)
@limiter.limit("5/minute")
async def root(request: Request, response: Response) -> JSONResponse:
    """
    Root endpoint.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Current response context.

    Returns
    -------
    JSONResponse
        Welcome message payload.

    Examples
    --------
    Request
        GET /
    Response
        200 OK
        {"message": "Welcome to BaliBlissed Backend"}
    """
    return JSONResponse(content={"message": "Welcome to BaliBlissed Backend"})
