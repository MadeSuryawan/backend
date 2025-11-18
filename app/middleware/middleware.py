"""Middleware components for the FastAPI Redis Cache application.

This module contains middleware functions for security headers,
request logging, CORS handling, and compression. This module also
contains the lifespan event handler for service initialization and
cleanup.
"""

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from logging import basicConfig, getLogger
from pathlib import Path
from time import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from rich.logging import RichHandler
from rich.traceback import install

from app.configs.settings import settings
from app.managers.cache_manager import cache_manager
from app.utils.helpers import file_logger

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

        await cache_manager.initialize()

        # Initialize AI client
        # get_ai_client()

        # Initialize email service
        # await email_service.initialize()

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
        # await cache_service.close()
        # await rate_limiter.close()
        await cache_manager.shutdown()
        logger.info("Cache manager stopped")
        logger.info("Services cleaned up successfully")

    except Exception:
        logger.exception("Error during service cleanup")


def add_security_headers(app: FastAPI) -> None:
    """Add security headers middleware to the application."""

    @app.middleware("http")
    async def add_security_headers_middleware(  # type: ignore
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Add security headers to all responses."""
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


def add_request_logging(app: FastAPI) -> None:
    """Add request logging middleware to the application."""

    @app.middleware("http")
    async def log_requests_middleware(  # type: ignore
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Log all incoming requests with timing information."""
        start_time: float = time()
        client_ip: str = request.client.host if request.client else "unknown"

        logger.info(f"Request: {request.method} {request.url.path} from {client_ip}")

        response = await call_next(request)

        process_time: float = time() - start_time
        logger.info(
            f"Response: {response.status_code} for {request.method} {request.url.path} "
            f"in {process_time:.4f}s",
        )

        return response


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


def add_compression(app: FastAPI) -> None:
    """Add compression middleware to the application."""
    app.add_middleware(GZipMiddleware, minimum_size=1000)
