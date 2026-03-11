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

from asyncio import get_running_loop
from collections.abc import AsyncGenerator, MutableMapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

from anyio import Path as AsyncPath
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from rich.traceback import install
from starlette.datastructures import MutableHeaders
from starlette.routing import BaseRoute, Match, Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from uvloop import Loop

from app.clients.ai_client import AiClient
from app.configs.settings import settings
from app.db import close_db, init_db
from app.logging import bind_request_id, clear_context, get_logger
from app.managers.cache_manager import CacheManager
from app.managers.login_attempt_tracker import init_login_tracker
from app.managers.rate_limiter import close_limiter
from app.managers.token_blacklist import init_token_blacklist
from app.monitoring import HealthChecker
from app.stores.idempotency import RedisIdempotencyStore
from app.utils.helpers import host, time_taken
from app.utils.timezone import format_logs

logger = get_logger(__name__)

# Install rich tracebacks for better error display
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
    logger.info(f"Starting {app.title}...")
    logger.info(f"{app.description}")

    try:
        cache_manager = await _init_services(app)
    except Exception:
        logger.exception("Failed to initialize services")
        raise

    yield

    logger.info(f"Shutting down {app.title}...")

    try:
        await _cleanup_services(app, cache_manager)
    except Exception:
        logger.exception("Error during service cleanup")


async def _init_services(app: FastAPI) -> CacheManager:
    """Initialize services."""
    if settings.LOG_TO_FILE:
        await AsyncPath("logs").mkdir(parents=True, exist_ok=True)
        logger.info("Logging to file enabled.")

    await init_db()

    app.state.health_checker = HealthChecker(
        app=app,
        version=app.version,
    )
    logger.info("Health checker initialized")

    cache_manager = CacheManager()
    await cache_manager.initialize()
    app.state.cache_manager = cache_manager

    _blacklist_and_tracker_init(app, cache_manager)

    logger.info(f"is uvloop: {type(get_running_loop()) is Loop}")

    if ai_client := AiClient():
        app.state.ai_client = ai_client

    logger.info("Services initialized successfully")
    _show_links()

    return cache_manager


def _blacklist_and_tracker_init(app: FastAPI, cache_manager: CacheManager) -> None:
    """Initialize token blacklist, login tracker, and idempotency store if Redis is available."""
    if cache_manager.is_redis_available:
        redis_client = cache_manager.redis_client
        token_blacklist = init_token_blacklist(redis_client)
        logger.info("Token blacklist initialized")
        login_tracker = init_login_tracker(redis_client)
        logger.info("Login attempt tracker initialized")
        app.state.token_blacklist = token_blacklist
        app.state.login_tracker = login_tracker

        # Idempotency store — backed by the same Redis connection.
        app.state.idempotency_store = RedisIdempotencyStore(redis_client.client)
        logger.info("Idempotency store initialized")


def _show_links() -> None:
    """Show links to services."""
    logger.info("Services:")
    logger.info("  - Backend API: http://localhost:8000")
    logger.info("  - API Documentation: http://localhost:8000/docs")
    logger.info("  - API Documentation (ReDoc): http://localhost:8000/redoc")
    logger.info("  - Health Check: http://localhost:8000/health")
    logger.info("  - Health Live: http://localhost:8000/health/live")
    logger.info("  - Health Ready: http://localhost:8000/health/ready")
    logger.info("  - Metrics: http://localhost:8000/metrics")
    logger.info("  - Legacy Metrics: http://localhost:8000/metrics/legacy")
    logger.info("  - Grafana: http://localhost:3000")
    logger.info("  - Prometheus: http://localhost:9090")
    logger.info("  - Jaeger UI: http://localhost:16686")
    logger.info("  - Redis Commander (dev profile): http://localhost:8081")


async def _cleanup_services(app: FastAPI, cache_manager: CacheManager) -> None:
    """Cleanup services on shutdown."""
    if ai_client := app.state.ai_client:
        await ai_client.close()
    await close_db()
    await close_limiter()
    await cache_manager.shutdown()
    logger.info("Cache manager stopped")
    logger.info("Services cleaned up successfully")


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


class LoggingMiddleware:
    """
    Middleware for logging request and response information.

    Logs request details including method, path, client IP, and
    response status code with timing information. Binds request_id
    for log correlation.

    Examples
    --------
    >>> from fastapi import FastAPI
    >>> app = FastAPI()
    >>> app.add_middleware(LoggingMiddleware)
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """
        Log request summary and timing information.

        Processes the request through the middleware chain and logs
        request details and response timing. Binds a request_id to
        the logging context for correlation.

        Parameters
        ----------
        scope : Scope
            The incoming ASGI connection scope.
        receive : Receive
            ASGI receive callable.
        send : Send
            ASGI send callable.
        """
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive=receive)

        # Generate and bind request ID for log correlation
        request_id = str(uuid4())[:8]
        bind_request_id(request_id)

        # Check if path should be excluded from logs
        should_log = request.url.path not in settings.log_excluded_paths_list

        start_time = perf_counter()
        bali_time, route_info, client_ip = self._get_kwargs(request)

        if should_log:
            logger.info(
                "Request started",
                path=request.url.path,
                route_info=route_info,
                client_ip=client_ip,
                bali_time=bali_time,
            )

        async def patched_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id

                if should_log:
                    logger.info(
                        "Request completed",
                        path=request.url.path,
                        status_code=message["status"],
                        duration=time_taken(start_time),
                    )

            await send(message)

        try:
            await self._app(scope, receive, patched_send)
        finally:
            # Clear context after request
            clear_context()

    def _get_kwargs(self, request: Request) -> tuple[str | None, str, str]:
        """Extract kwargs from request."""

        # Log in Bali timezone for server/admin visibility
        bali_time = format_logs(datetime.now(UTC), settings.TZ)
        route_info = self._get_summary(request) or f"{request.method} {request.url.path}"
        client_ip = host(request)

        return bali_time, route_info, client_ip

    def _get_summary(self, request: Request) -> str | None:
        """Extract route summary from request."""

        scope: MutableMapping[str, Any] = request.scope
        app: FastAPI = scope["app"]
        routes: list[BaseRoute] = app.routes

        summary = None
        for route in routes:
            is_api_route = type(route) is APIRoute
            is_route = type(route) is Route
            if is_api_route and route.matches(scope)[0] == Match.FULL:
                summary = route.summary
                break
            if is_route and route.matches(scope)[0] == Match.FULL:
                summary = route.name
                break

        return summary


class SecurityHeadersMiddleware:
    """
    Pure-ASGI middleware that injects security headers into every response.

    Unlike ``BaseHTTPMiddleware``, this implementation operates directly on
    the ASGI send-callable, so it never buffers the response body.  This
    makes it safe for streaming endpoints and eliminates the per-request
    overhead that ``BaseHTTPMiddleware`` incurs when wrapping the body.

    Headers injected
    ----------------
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

    _SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"x-xss-protection", b"1; mode=block"),
        (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
    )

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        async def patched_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(self._SECURITY_HEADERS)
                message = {**message, "headers": headers}
            await send(message)

        await self._app(scope, receive, patched_send)
