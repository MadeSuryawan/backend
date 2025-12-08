# app/main.py
"""BaliBlissed Backend - Seamless caching integration with Redis for FastAPI."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, ORJSONResponse, Response
from slowapi.errors import RateLimitExceeded
from starlette.responses import JSONResponse
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.errors import (
    AiError,
    CacheExceptionError,
    CircuitBreakerError,
    DatabaseError,
    EmailServiceError,
    PasswordHashingError,
    ai_exception_handler,
    cache_exception_handler,
    circuit_breaker_exception_handler,
    database_exception_handler,
    email_client_exception_handler,
    password_hashing_exception_handler,
    validation_exception_handler,
)
from app.managers import (
    cache_manager,
    get_system_metrics,
    limiter,
    metrics_manager,
    rate_limit_exceeded_handler,
)
from app.managers.circuit_breaker import ai_circuit_breaker, email_circuit_breaker
from app.middleware import (
    LoggingMiddleware,
    SecurityHeadersMiddleware,
    configure_cors,
    lifespan,
)
from app.routes import ai_router, cache_router, email_router, get_email_client, items_router
from app.schemas import HealthCheckResponse
from app.schemas.cache import CacheHealthResponse, ServicesStatus
from app.utils import today_str

app = FastAPI(
    title="BaliBlissed Backend",
    description="Seamless caching integration with Redis for FastAPI",
    version="1.0.0",
    lifespan=lifespan,
)

configure_cors(app)

app.add_middleware(LoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)
# Middleware to tell FastAPI it is behind a proxy (Zuplo) or Render
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

app.include_router(cache_router)
app.include_router(email_router)
app.include_router(items_router)
app.include_router(ai_router)


app.add_exception_handler(
    CacheExceptionError,
    cache_exception_handler,
)
app.add_exception_handler(
    RateLimitExceeded,
    rate_limit_exceeded_handler,
)
app.add_exception_handler(
    EmailServiceError,
    email_client_exception_handler,
)
app.add_exception_handler(
    CircuitBreakerError,
    circuit_breaker_exception_handler,
)
app.add_exception_handler(
    PasswordHashingError,
    password_hashing_exception_handler,
)
app.add_exception_handler(
    DatabaseError,
    database_exception_handler,
)
app.add_exception_handler(
    AiError,
    ai_exception_handler,
)
app.add_exception_handler(
    RequestValidationError,
    validation_exception_handler,
)


@app.get(
    "/",
    tags=["root"],
    summary="Root access",
    response_model=dict[str, str],
    response_class=JSONResponse,
)
@limiter.limit("5/minute")
async def root(request: Request, response: Response) -> JSONResponse:
    """Root endpoint."""
    response.headers["X-Frame-Options"] = "DENY"
    return JSONResponse(content={"message": "Welcome to BaliBlissed Backend"})


@app.get(
    "/health",
    tags=["health"],
    summary="Health check endpoint",
    response_model=HealthCheckResponse,
    response_class=ORJSONResponse,
)
@limiter.exempt
async def health_check(request: Request) -> ORJSONResponse:
    """Health check endpoint with comprehensive status."""
    # Get cache health info
    cache_health_data = await cache_manager.health_check()

    # Determine AI client status
    ai_client_status = (
        "initialized"
        if hasattr(request.app.state, "ai_client") and request.app.state.ai_client
        else "not_initialized"
    )

    # Determine Email client status (check if credentials are configured)
    try:
        email_client = get_email_client()
        # Check if service can be initialized (credentials available)
        email_client_status = "available" if email_client.service else "not_configured"
    except EmailServiceError:
        email_client_status = "not_configured"

    # Build services status
    services = ServicesStatus(
        ai_client=ai_client_status,
        email_client=email_client_status,
        ai_circuit_breaker=ai_circuit_breaker.get_state(),
        email_circuit_breaker=email_circuit_breaker.get_state(),
    )

    # Build response
    response_data = {
        "version": request.app.version,
        "timestamp": today_str(),
        "services": services.model_dump(),
        "cache": CacheHealthResponse(**cache_health_data).model_dump(),
    }

    return ORJSONResponse(response_data)


@app.get("/favicon.ico", include_in_schema=False)
async def get_favicon() -> FileResponse:
    """Get favicon."""

    return FileResponse("favicon.ico")


@app.get(
    "/metrics",
    tags=["metrics"],
    response_class=ORJSONResponse,
    summary="Get metrics",
    description="Get API performance metrics.",
)
@limiter.limit("5/minute")
async def get_metrics(request: Request, response: Response) -> ORJSONResponse:
    """
    Get API performance metrics.

    Returns:
        Dictionary containing performance metrics
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


if __name__ == "__main__":
    from uvicorn import run

    run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="info",
        reload=True,
        loop="uvloop",
        http="httptools",
    )
