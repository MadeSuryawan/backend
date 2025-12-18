# app/middleware/middleware.py
"""
Middleware components for the FastAPI Redis Cache application.

This module contains middleware functions for security headers,
request logging, CORS handling, and compression. This module also
contains the lifespan event handler for service initialization and
cleanup.
"""

from asyncio import get_event_loop
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from logging import basicConfig, getLogger
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pythonjsonlogger.json import JsonFormatter
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

if log_to_file := settings.LOG_TO_FILE:
    Path("logs").mkdir(parents=True, exist_ok=True)

# --- Logging Configuration ---
basicConfig(
    level="NOTSET",
    format="%(message)s",
    datefmt="%X",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logger = getLogger("rich")
file_logger(logger)
for handler in logger.handlers:
    handler.setFormatter(JsonFormatter())

install()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Manage application startup and shutdown events with service initialization."""
    # Startup
    logger.info(f"Starting {app.title}...")
    logger.info(f"{app.description}")

    # Initialize services
    try:
        if log_to_file:
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
    """Configure CORS middleware for the application."""
    # Determine allowed origins based on environment
    allowed_origins: list[str] = [
        "http://localhost:3000",  # Next.js development
        "http://127.0.0.1:3000",
    ]

    # Add production origins if specified
    if frontend_url := settings.PRODUCTION_FRONTEND_URL:
        allowed_origins.append(frontend_url)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Log request summary and timing information."""

        start_time = perf_counter()
        summary = get_summary(request)

        route_info = summary or f"{request.method} {request.url.path}"
        logger.info(f"Request: {route_info}, from ip: {host(request)}")

        response = await call_next(request)
        duration = perf_counter() - start_time

        logger.info(
            f"Response: {response.status_code} for {request.method} {request.url.path} "
            f"in {duration:.2f}s\n",
        )

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Add security headers to all responses."""

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
