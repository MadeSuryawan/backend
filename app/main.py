# app/main.py

"""BaliBlissed Backend - Seamless caching integration with Redis for FastAPI."""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.configs.settings import settings
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
from app.logging import configure_logging, get_logger
from app.managers.rate_limiter import rate_limit_exceeded_handler
from app.middleware import (
    IdempotencyMiddleware,
    LoggingMiddleware,
    SecurityHeadersMiddleware,
    TimezoneMiddleware,
    configure_cors,
    lifespan,
)
from app.middleware.context import ContextMiddleware
from app.monitoring import setup_prometheus, setup_tracing
from app.routes import (
    admin_router,
    ai_router,
    auth_router,
    blog_router,
    cache_router,
    email_router,
    health_router,
    items_router,
    limiter_router,
    oauth_router,
    review_router,
    user_router,
)

configure_logging()
logger = get_logger(__name__)

# Configure API documentation endpoints based on settings
app = FastAPI(
    title="BaliBlissed Backend",
    description="BaliBlissed Travel Agency Backend API",
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

# Set up Prometheus metrics (must be before other middleware)
instrumentator = setup_prometheus(app)

# Set up OpenTelemetry tracing
setup_tracing(app)

# Configure CORS
configure_cors(app)

# Timezone detection middleware (must be early to set request.state.user_timezone)
app.add_middleware(TimezoneMiddleware)  # type: ignore[arg-type]  # pure-ASGI stub limitation
app.add_middleware(LoggingMiddleware)  # type: ignore[arg-type]  # pure-ASGI stub limitation
app.add_middleware(SecurityHeadersMiddleware)  # type: ignore[arg-type]  # pure-ASGI stub limitation
# Idempotency middleware — store is lazily resolved from app.state after lifespan.
# Must run after authentication context is available (inner middleware runs first).
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.add_middleware(GZipMiddleware, minimum_size=1000)
# Middleware to tell FastAPI it is behind a proxy (Zuplo) or Render
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.trusted_hosts_list)
# Trusted Host middleware to validate Host headers
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts_list)
# Middleware to set context variables for decorators
app.add_middleware(ContextMiddleware)  # type: ignore[arg-type]  # pure-ASGI stub limitation


routes = (
    health_router,
    admin_router,
    auth_router,
    oauth_router,
    ai_router,
    email_router,
    user_router,
    blog_router,
    items_router,
    review_router,
    cache_router,
    limiter_router,
)

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

errors = (
    (CacheExceptionError, cache_exception_handler),
    (RateLimitExceeded, rate_limit_exceeded_handler),
    (EmailServiceError, email_client_exception_handler),
    (CircuitBreakerError, circuit_breaker_exception_handler),
    (PasswordHashingError, password_hashing_exception_handler),
    (UserAuthenticationError, auth_exception_handler),
    (DatabaseError, database_exception_handler),
    (AiError, ai_exception_handler),
    (RequestValidationError, validation_exception_handler),
)

_ = [app.add_exception_handler(exc_type, handler) for exc_type, handler in errors]


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
