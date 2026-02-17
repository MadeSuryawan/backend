# app/middleware/middleware.py
"""
Middleware components for the FastAPI application.

This module provides middleware functions for security headers,
request logging, CORS handling, and application lifecycle management.
It also contains the lifespan event handler for service initialization
and cleanup.

Modules
-------
lifespan : asynccontextmanager
    Manages application startup and shutdown events.
configure_cors : function
    Configures CORS middleware for the application.
LoggingMiddleware : class
    Logs request summary and timing information.
SecurityHeadersMiddleware : class
    Adds security headers to all responses.

Examples
--------
>>> from app.middleware import lifespan, configure_cors
>>> app = FastAPI(lifespan=lifespan)
>>> configure_cors(app)
"""

from asyncio import get_event_loop
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from logging import basicConfig, getLogger
from time import perf_counter

from anyio import Path as AsyncPath
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from rich.logging import RichHandler
from rich.traceback import install
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from uvloop import Loop

from app.clients.ai_client import AiClient
from app.configs import settings
from app.db import close_db, init_db
from app.managers.cache_manager import CacheManager
from app.managers.login_attempt_tracker import init_login_tracker
from app.managers.rate_limiter import close_limiter
from app.managers.token_blacklist import init_token_blacklist
from app.utils.helpers import file_logger, get_summary, host
from app.utils.timezone import format_logs

# --- Logging Configuration ---
basicConfig(
    level=settings.LOG_LEVEL,
    format="%(message)s",
    datefmt="%X",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logger = getLogger("rich")
file_logger(logger)

install()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Manage application startup and shutdown events.

    This context manager handles the initialization and cleanup of
    all application services including database, cache manager,
    token blacklist, and AI client.

    Parameters
    ----------
    app : FastAPI
        The FastAPI application instance.

    Yields
    ------
    None
        Control is yielded to the application during its lifetime.

    Raises
    ------
    Exception
        If service initialization fails during startup.

    Examples
    --------
    >>> app = FastAPI(lifespan=lifespan)
    """
    # Startup
    logger.info(f"Starting {app.title}...")
    logger.info(f"{app.description}")

    # Initialize services
    try:
        if settings.LOG_TO_FILE:
            await AsyncPath("logs").mkdir(parents=True, exist_ok=True)
            logger.info("Logging to file enabled.")

        await init_db()

        cache_manager = CacheManager()
        await cache_manager.initialize()
        app.state.cache_manager = cache_manager

        # Initialize token blacklist and login tracker if Redis is available
        if cache_manager.is_redis_available:
            init_token_blacklist(cache_manager.redis_client)
            init_login_tracker(cache_manager.redis_client)
            logger.info("Token blacklist and login tracker initialized")

        logger.info(f"is uvloop: {type(get_event_loop()) is Loop}")

        if ai_client := AiClient():
            app.state.ai_client = ai_client
            logger.info("AI client initialized successfully.")

        logger.info("Services initialized successfully")
        logger.info("Services:")
        logger.info("  - Backend API: http://localhost:8000")
        logger.info("  - API Documentation: http://localhost:8000/docs")
        logger.info("  - API Documentation (ReDoc): http://localhost:8000/redoc")
        logger.info("  - Health Check: http://localhost:8000/health")
        logger.info("  - Metrics: http://localhost:8000/metrics")
        logger.info("  - Redis Commander: http://localhost:8081")

    except Exception:
        logger.exception("Failed to initialize services")
        raise

    yield

    # Shutdown
    logger.info(f"Shutting down {app.title}...")

    # Cleanup services
    try:
        # Shutdown monitoring first to flush pending traces/metrics
        from app.monitoring import shutdown_monitoring

        shutdown_monitoring()

        if ai_client := app.state.ai_client:
            await ai_client.close()
        await close_db()
        await close_limiter()
        await cache_manager.shutdown()
        logger.info("Cache manager stopped")
        logger.info("Services cleaned up successfully")

    except Exception:
        logger.exception("Error during service cleanup")


def configure_cors(app: FastAPI) -> None:
    """
    Configure CORS middleware for the application.

    Sets up Cross-Origin Resource Sharing (CORS) policies based on
    CORS_ORIGINS setting from environment configuration.

    Parameters
    ----------
    app : FastAPI
        The FastAPI application instance to configure.

    Notes
    -----
    Allowed origins are read from the CORS_ORIGINS environment variable,
    which should be a comma-separated list of allowed origins.

    Examples
    --------
    >>> from fastapi import FastAPI
    >>> app = FastAPI()
    >>> configure_cors(app)
    """
    # Get allowed origins from settings
    allowed_origins = settings.cors_origins_list

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for logging request and response information.

    Logs request details including method, path, client IP, and
    response status code with timing information.

    Examples
    --------
    >>> from fastapi import FastAPI
    >>> app = FastAPI()
    >>> app.add_middleware(LoggingMiddleware)
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """
        Log request summary and timing information.

        Processes the request through the middleware chain and logs
        request details and response timing.

        Parameters
        ----------
        request : Request
            The incoming HTTP request.
        call_next : RequestResponseEndpoint
            The next middleware or endpoint in the chain.

        Returns
        -------
        Response
            The HTTP response from the downstream handler.

        Examples
        --------
        >>> response = await middleware.dispatch(request, call_next)
        """

        start_time = perf_counter()
        summary = get_summary(request)

        # Log in Bali timezone for server/admin visibility
        bali_time = format_logs(datetime.now(UTC), settings.TZ)
        route_info = summary or f"{request.method} {request.url.path}"
        logger.info(f"[{bali_time}] Request: {route_info}, from ip: {host(request)}")

        response = await call_next(request)
        duration = perf_counter() - start_time

        logger.info(
            f"Response: {response.status_code} for {request.method} {request.url.path} "
            f"in {duration:.2f}s\n",
        )

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware for adding security headers to responses.

    Adds security-related HTTP headers to all responses including
    XSS protection, content type options, frame options, and
    strict transport security.

    Headers Added
    -------------
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Strict-Transport-Security: max-age=31536000; includeSubDomains
    - Referrer-Policy: strict-origin-when-cross-origin

    Examples
    --------
    >>> from fastapi import FastAPI
    >>> app = FastAPI()
    >>> app.add_middleware(SecurityHeadersMiddleware)
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """
        Add security headers to all responses.

        Processes the request and adds security headers to the
        response before returning it to the client.

        Parameters
        ----------
        request : Request
            The incoming HTTP request.
        call_next : RequestResponseEndpoint
            The next middleware or endpoint in the chain.

        Returns
        -------
        Response
            The HTTP response with security headers added.

        Examples
        --------
        >>> response = await middleware.dispatch(request, call_next)
        """

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
