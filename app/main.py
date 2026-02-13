# app/main.py

"""BaliBlissed Backend - Seamless caching integration with Redis for FastAPI."""

from os import environ

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, ORJSONResponse, Response
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.configs import settings

# Set timezone for consistent datetime handling
environ["TZ"] = settings.TZ
from app.decorators.caching import get_cache_manager
from app.dependencies import EmailDep
from app.errors import (
    AiError,
    CacheExceptionError,
    CircuitBreakerError,
    DatabaseError,
    EmailServiceError,
    PasswordHashingError,
    UserAuthenticationError,
    ai_exception_handler,
    auth_exception_handler,
    cache_exception_handler,
    circuit_breaker_exception_handler,
    database_exception_handler,
    email_client_exception_handler,
    password_hashing_exception_handler,
    validation_exception_handler,
)
from app.managers.circuit_breaker import ai_circuit_breaker, email_circuit_breaker
from app.managers.metrics import get_system_metrics, metrics_manager
from app.managers.rate_limiter import limiter, rate_limit_exceeded_handler
from app.middleware import (
    LoggingMiddleware,
    SecurityHeadersMiddleware,
    TimezoneMiddleware,
    configure_cors,
    lifespan,
)
from app.middleware.context import ContextMiddleware
from app.routes import (
    admin_router,
    ai_router,
    auth_router,
    blog_router,
    cache_router,
    email_router,
    items_router,
    limiter_router,
    review_router,
    user_router,
)
from app.schemas import HealthCheckResponse
from app.schemas.cache import CacheHealthResponse, CircuitBreakerStatus, ServicesStatus
from app.utils.helpers import today_str

# Configure API documentation endpoints based on settings
app = FastAPI(
    title="BaliBlissed Backend",
    description="BaliBlissed Backend API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DOCS_ENABLED else None,
    redoc_url="/redoc" if settings.DOCS_ENABLED else None,
    openapi_url="/openapi.json" if settings.DOCS_ENABLED else None,
    swagger_ui_parameters={
        "docExpansion": "none",
        "operationsSorter": "method",
    },
)

configure_cors(app)

# Timezone detection middleware (must be early to set request.state.user_timezone)
app.add_middleware(TimezoneMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.add_middleware(GZipMiddleware, minimum_size=1000)
# Middleware to tell FastAPI it is behind a proxy (Zuplo) or Render
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.trusted_hosts_list)
# Trusted Host middleware to validate Host headers
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts_list)
# Middleware to set context variables for decorators
app.add_middleware(ContextMiddleware)


routes = [
    admin_router,
    auth_router,
    ai_router,
    email_router,
    user_router,
    blog_router,
    items_router,
    review_router,
    cache_router,
    limiter_router,
]

_ = [app.include_router(router) for router in routes]

# Mount static files for local uploads (only if using local storage)
if settings.STORAGE_PROVIDER == "local":
    # Ensure uploads directory exists
    settings.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/uploads",
        StaticFiles(directory=str(settings.UPLOADS_DIR)),
        name="uploads",
    )

errors = [
    (CacheExceptionError, cache_exception_handler),
    (RateLimitExceeded, rate_limit_exceeded_handler),
    (EmailServiceError, email_client_exception_handler),
    (CircuitBreakerError, circuit_breaker_exception_handler),
    (PasswordHashingError, password_hashing_exception_handler),
    (UserAuthenticationError, auth_exception_handler),
    (DatabaseError, database_exception_handler),
    (AiError, ai_exception_handler),
    (RequestValidationError, validation_exception_handler),
]

_ = [app.add_exception_handler(exc_type, handler) for exc_type, handler in errors]

app.state.limiter = limiter
limiter: Limiter = app.state.limiter


if settings.HEALTH_CHECK_ENABLED:

    @app.get(
        settings.HEALTH_CHECK_ENDPOINT,
        tags=["🩺 Health"],
        summary="Health check endpoint",
        response_model=HealthCheckResponse,
        response_class=ORJSONResponse,
        responses={
            200: {
                "content": {
                    "application/json": {
                        "example": {
                            "version": "1.0.0",
                            "status": "ok",
                            "timestamp": "2025-01-01",
                            "services": {
                                "ai_client": "initialized",
                                "email_client": "available",
                                "ai_circuit_breaker": "closed",
                                "email_circuit_breaker": "closed",
                            },
                            "cache": {"status": "healthy"},
                        },
                    },
                },
            },
        },
        operation_id="health_check",
    )
    @limiter.exempt
    async def health_check(request: Request, email_client: EmailDep) -> ORJSONResponse:
        """
        Health check endpoint with comprehensive status.

        Parameters
        ----------
        request : Request
            Current request context.
        email_client : EmailDep
            Email client dependency.

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
            {"version": "1.0.0", "status": "ok", "timestamp": "2025-01-01", "services": { ... }, "cache": { ... }}
        """
        # Get cache health info
        cache_health_data = await get_cache_manager(request).health_check()

        # Determine AI client status
        ai_client_status = (
            "initialized"
            if hasattr(request.app.state, "ai_client") and request.app.state.ai_client
            else "not_initialized"
        )

        # Determine Email client status (check if credentials are configured)
        try:
            # Check if service can be initialized (credentials available)
            email_client_status = "available" if email_client.service else "not_configured"
        except EmailServiceError:
            email_client_status = "not_configured"

        # Build services status
        services = ServicesStatus(
            ai_client=ai_client_status,
            email_client=email_client_status,
            ai_circuit_breaker=CircuitBreakerStatus(**ai_circuit_breaker.get_state()),
            email_circuit_breaker=CircuitBreakerStatus(**email_circuit_breaker.get_state()),
        )

        # Build response
        response_data = {
            "version": app.version,
            "status": "ok",
            "timestamp": today_str(),
            "services": services.model_dump(),
            "cache": CacheHealthResponse(**cache_health_data).model_dump(),
        }

        return ORJSONResponse(response_data)


@app.get("/favicon.ico", tags=["🖼️ Assets"], include_in_schema=False)
async def get_favicon() -> FileResponse:
    """Get favicon."""

    return FileResponse("favicon.ico")


@app.get(
    "/metrics",
    tags=["📈 Metrics"],
    response_class=ORJSONResponse,
    summary="Get metrics",
    description="Get API performance metrics.",
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
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="get_metrics",
)
@limiter.limit("5/minute")
async def get_metrics(request: Request, response: Response) -> ORJSONResponse:
    """
    Get API performance metrics.

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
        GET /metrics
    Response
        200 OK
        {"timestamp": "2025-01-01", "api_metrics": { ... }, "system_metrics": { ... }}
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


@app.get(
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
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
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

    Notes
    -----
    Rate limited to 5 requests per minute.

    Examples
    --------
    Request
        GET /
    Response
        200 OK
        {"message": "Welcome to BaliBlissed Backend"}

    Response schema
    ---------------
    {
      "message": str
    }
    """
    return JSONResponse(content={"message": "Welcome to BaliBlissed Backend"})


if __name__ == "__main__":
    from uvicorn import run

    run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_level=settings.LOG_LEVEL.lower(),
        reload=settings.DEBUG,
        loop="uvloop",
        http="httptools",
        timeout_keep_alive=settings.REQUEST_TIMEOUT,
    )
