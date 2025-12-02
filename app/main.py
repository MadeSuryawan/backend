# app/main.py
"""BaliBlissed Backend - Seamless caching integration with Redis for FastAPI."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, ORJSONResponse, Response
from slowapi.errors import RateLimitExceeded

from app.errors import (
    CacheExceptionError,
    EmailServiceError,
    cache_exception_handler,
    email_service_exception_handler,
)
from app.managers import (
    cache_manager,
    get_system_metrics,
    limiter,
    metrics_manager,
    rate_limit_exceeded_handler,
)
from app.middleware import (
    LoggingMiddleware,
    SecurityHeadersMiddleware,
    configure_cors,
    lifespan,
)
from app.routes import cache_router, email_router, items_router
from app.schemas import HealthCheckResponse
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

app.include_router(cache_router)
app.include_router(email_router)
app.include_router(items_router)

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
    email_service_exception_handler,
)


@app.get("/", tags=["root"], summary="Root access", response_model=dict[str, str])
@limiter.exempt
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"message": "Welcome to FastAPI Redis Cache"}


@app.get(
    "/health",
    tags=["health"],
    summary="Health check endpoint",
    response_model=HealthCheckResponse,
    response_class=ORJSONResponse,
)
@limiter.exempt
async def health_check() -> ORJSONResponse:
    """Health check endpoint."""
    return ORJSONResponse(await cache_manager.health_check())


@app.get("/favicon.ico", include_in_schema=False)
async def get_favicon() -> FileResponse:
    """Get favicon."""

    parent_dir = Path(__file__).parent
    return FileResponse(parent_dir / "favicon.ico")


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
        {
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
