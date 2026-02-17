"""
Kubernetes-compatible health check endpoints for BaliBlissed Backend.

This module provides health check endpoints following Kubernetes conventions:
- /health/live: Liveness probe - basic app responsiveness
- /health/ready: Readiness probe - dependency checks (DB, Redis)
- /health: Combined status for backward compatibility

Health Check Strategy:
    - Liveness: No external dependencies, fast response
    - Readiness: Checks all critical dependencies with timeouts
    - Graceful degradation: Returns appropriate status codes

Timeout Configuration:
    - Database: 2 seconds
    - Redis: 1 second
    - External APIs: 3 seconds
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from enum import Enum
from logging import getLogger
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.configs import settings

if TYPE_CHECKING:
    from fastapi import FastAPI, Request

logger = getLogger(__name__)

# --- Constants ---
HEALTH_CHECK_TIMEOUTS = {
    "database": 2.0,  # seconds
    "redis": 1.0,
    "external_api": 3.0,
}

# Disk usage threshold (percentage)
DISK_USAGE_WARNING_THRESHOLD = 80
DISK_USAGE_CRITICAL_THRESHOLD = 90

# Memory usage threshold (percentage)
MEMORY_USAGE_WARNING_THRESHOLD = 80
MEMORY_USAGE_CRITICAL_THRESHOLD = 90


class HealthStatus(str, Enum):
    """Health check status values."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class ComponentHealth(BaseModel):
    """Health status for a single component."""

    status: HealthStatus
    response_ms: float | None = None
    message: str | None = None
    details: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    """Health check response model."""

    status: HealthStatus
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    version: str = "1.0.0"
    checks: dict[str, ComponentHealth] = Field(default_factory=dict)


class LivenessResponse(BaseModel):
    """Liveness probe response model."""

    status: HealthStatus
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


async def check_database_health() -> ComponentHealth:
    """
    Check database connectivity and responsiveness.

    Returns
    -------
    ComponentHealth
        Database health status with response time.
    """
    import time

    from sqlalchemy import text

    from app.db.database import engine

    start_time = time.perf_counter()

    try:
        async with asyncio.timeout(HEALTH_CHECK_TIMEOUTS["database"]):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

        response_ms = (time.perf_counter() - start_time) * 1000

        return ComponentHealth(
            status=HealthStatus.PASS,
            response_ms=round(response_ms, 2),
        )

    except TimeoutError:
        return ComponentHealth(
            status=HealthStatus.FAIL,
            message="Database health check timed out",
            response_ms=HEALTH_CHECK_TIMEOUTS["database"] * 1000,
        )
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        return ComponentHealth(
            status=HealthStatus.FAIL,
            message=str(e),
        )


async def check_redis_health(request: Request) -> ComponentHealth:
    """
    Check Redis connectivity and responsiveness.

    Parameters
    ----------
    request : Request
        The current request (to access app state).

    Returns
    -------
    ComponentHealth
        Redis health status with response time.
    """
    import time

    start_time = time.perf_counter()

    try:
        cache_manager = getattr(request.app.state, "cache_manager", None)
        if cache_manager is None:
            return ComponentHealth(
                status=HealthStatus.WARN,
                message="Cache manager not initialized",
            )

        async with asyncio.timeout(HEALTH_CHECK_TIMEOUTS["redis"]):
            health_data = await cache_manager.health_check()

        response_ms = (time.perf_counter() - start_time) * 1000

        # Determine status based on cache health
        if health_data.get("status") == "healthy":
            status = HealthStatus.PASS
        elif health_data.get("fallback_active"):
            status = HealthStatus.WARN
        else:
            status = HealthStatus.FAIL

        return ComponentHealth(
            status=status,
            response_ms=round(response_ms, 2),
            details=health_data,
        )

    except TimeoutError:
        return ComponentHealth(
            status=HealthStatus.FAIL,
            message="Redis health check timed out",
            response_ms=HEALTH_CHECK_TIMEOUTS["redis"] * 1000,
        )
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        return ComponentHealth(
            status=HealthStatus.WARN,
            message=str(e),
        )


async def check_disk_health() -> ComponentHealth:
    """
    Check disk space availability.

    Returns
    -------
    ComponentHealth
        Disk health status with usage percentage.
    """
    try:
        from psutil import disk_usage

        disk = disk_usage("/")
        usage_percent = disk.percent

        if usage_percent >= DISK_USAGE_CRITICAL_THRESHOLD:
            status = HealthStatus.FAIL
            message = f"Disk usage critical: {usage_percent:.1f}%"
        elif usage_percent >= DISK_USAGE_WARNING_THRESHOLD:
            status = HealthStatus.WARN
            message = f"Disk usage warning: {usage_percent:.1f}%"
        else:
            status = HealthStatus.PASS
            message = None

        return ComponentHealth(
            status=status,
            message=message,
            details={
                "usage_percent": round(usage_percent, 1),
                "total_gb": round(disk.total / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
            },
        )

    except Exception as e:
        logger.warning(f"Disk health check failed: {e}")
        return ComponentHealth(
            status=HealthStatus.WARN,
            message=str(e),
        )


async def check_memory_health() -> ComponentHealth:
    """
    Check memory availability.

    Returns
    -------
    ComponentHealth
        Memory health status with usage percentage.
    """
    try:
        from psutil import virtual_memory

        mem = virtual_memory()
        usage_percent = mem.percent

        if usage_percent >= MEMORY_USAGE_CRITICAL_THRESHOLD:
            status = HealthStatus.FAIL
            message = f"Memory usage critical: {usage_percent:.1f}%"
        elif usage_percent >= MEMORY_USAGE_WARNING_THRESHOLD:
            status = HealthStatus.WARN
            message = f"Memory usage warning: {usage_percent:.1f}%"
        else:
            status = HealthStatus.PASS
            message = None

        return ComponentHealth(
            status=status,
            message=message,
            details={
                "usage_percent": round(usage_percent, 1),
                "total_gb": round(mem.total / (1024**3), 2),
                "available_gb": round(mem.available / (1024**3), 2),
            },
        )

    except Exception as e:
        logger.warning(f"Memory health check failed: {e}")
        return ComponentHealth(
            status=HealthStatus.WARN,
            message=str(e),
        )


async def perform_liveness_check() -> LivenessResponse:
    """
    Perform liveness check - basic app responsiveness only.

    This check should NOT include external dependencies.
    Kubernetes will restart the pod if this fails.

    Returns
    -------
    LivenessResponse
        Liveness status.
    """
    return LivenessResponse(status=HealthStatus.PASS)


async def perform_readiness_check(request: Request) -> HealthResponse:
    """
    Perform readiness check - verify all dependencies are available.

    Kubernetes will stop routing traffic if this fails.

    Parameters
    ----------
    request : Request
        The current request.

    Returns
    -------
    HealthResponse
        Readiness status with component details.
    """
    # Run all checks concurrently
    db_check, redis_check, disk_check, memory_check = await asyncio.gather(
        check_database_health(),
        check_redis_health(request),
        check_disk_health(),
        check_memory_health(),
        return_exceptions=True,
    )

    # Handle any exceptions from gather
    checks: dict[str, ComponentHealth] = {}

    if isinstance(db_check, ComponentHealth):
        checks["database"] = db_check
    else:
        checks["database"] = ComponentHealth(
            status=HealthStatus.FAIL,
            message=str(db_check),
        )

    if isinstance(redis_check, ComponentHealth):
        checks["redis"] = redis_check
    else:
        checks["redis"] = ComponentHealth(
            status=HealthStatus.WARN,
            message=str(redis_check),
        )

    if isinstance(disk_check, ComponentHealth):
        checks["disk"] = disk_check
    else:
        checks["disk"] = ComponentHealth(
            status=HealthStatus.WARN,
            message=str(disk_check),
        )

    if isinstance(memory_check, ComponentHealth):
        checks["memory"] = memory_check
    else:
        checks["memory"] = ComponentHealth(
            status=HealthStatus.WARN,
            message=str(memory_check),
        )

    # Determine overall status
    # FAIL if any critical component fails (database)
    # WARN if non-critical components have issues
    if checks["database"].status == HealthStatus.FAIL:
        overall_status = HealthStatus.FAIL
    elif any(c.status == HealthStatus.FAIL for c in checks.values()):
        overall_status = HealthStatus.FAIL
    elif any(c.status == HealthStatus.WARN for c in checks.values()):
        overall_status = HealthStatus.WARN
    else:
        overall_status = HealthStatus.PASS

    return HealthResponse(
        status=overall_status,
        version=settings.APP_NAME.split()[-1] if settings.APP_NAME else "1.0.0",
        checks=checks,
    )


def setup_health_routes(app: FastAPI) -> None:
    """
    Set up health check routes on the FastAPI application.

    Parameters
    ----------
    app : FastAPI
        The FastAPI application instance.
    """
    from fastapi import Request
    from fastapi.responses import JSONResponse

    @app.get(
        "/health/live",
        tags=["Health"],
        summary="Liveness probe",
        description="Basic app responsiveness check. No external dependencies.",
        response_model=LivenessResponse,
        responses={
            200: {"description": "Application is alive"},
            503: {"description": "Application is not responding"},
        },
    )
    async def liveness_probe() -> JSONResponse:
        """Liveness probe endpoint for Kubernetes."""
        response = await perform_liveness_check()
        return JSONResponse(
            content=response.model_dump(),
            status_code=200 if response.status == HealthStatus.PASS else 503,
        )

    @app.get(
        "/health/ready",
        tags=["Health"],
        summary="Readiness probe",
        description="Checks all dependencies (database, Redis, disk, memory).",
        response_model=HealthResponse,
        responses={
            200: {"description": "Application is ready to receive traffic"},
            503: {"description": "Application is not ready"},
        },
    )
    async def readiness_probe(request: Request) -> JSONResponse:
        """Readiness probe endpoint for Kubernetes."""
        response = await perform_readiness_check(request)

        if response.status == HealthStatus.PASS:
            status_code = 200
        elif response.status == HealthStatus.WARN:
            status_code = 200  # Still accept traffic with warnings
        else:
            status_code = 503

        return JSONResponse(
            content=response.model_dump(),
            status_code=status_code,
        )

    logger.info("Health check routes configured: /health/live, /health/ready")
