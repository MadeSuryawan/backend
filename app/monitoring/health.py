"""
Kubernetes-compatible health checks with dependency validation.

This module provides health check endpoints compatible with Kubernetes probes:
- /health/live (Liveness): Basic app responsiveness - no external deps
- /health/ready (Readiness): Database, Redis, and dependency checks
- /health (Combined): Backward compatibility endpoint

Timeouts
--------
- Database: 2 seconds
- Redis: 1 second
- External APIs: 3 seconds

Response Format
---------------
All endpoints return JSON with the following structure:
{
    "status": "ready" | "not_ready" | "error",
    "timestamp": "2025-01-01T12:00:00Z",
    "version": "1.0.0",
    "checks": {
        "database": {"status": "pass", "response_ms": 15},
        "redis": {"status": "pass", "response_ms": 5},
        "disk": {"status": "pass", "usage_percent": 45}
    }
}

Examples
--------
>>> from app.monitoring import HealthChecker, HealthStatus
>>> checker = HealthChecker()
>>> status = await checker.check_readiness()
>>> if status.is_healthy:
...     print("Service is ready")
"""

from asyncio import wait_for
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from time import perf_counter
from typing import Any

from fastapi import FastAPI
from psutil import disk_usage
from sqlalchemy import text

from app.db.database import transaction
from app.utils.helpers import today_str

# Health check timeouts (seconds)
HEALTH_CHECK_TIMEOUTS: dict[str, float] = {
    "database": 2.0,
    "redis": 1.0,
    "external_api": 3.0,
}


class CheckStatus(StrEnum):
    """Status values for individual health checks."""

    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"


class OverallStatus(StrEnum):
    """Overall health status."""

    READY = "ready"
    NOT_READY = "not_ready"
    ERROR = "error"
    LIVE = "live"


@dataclass
class ComponentCheck:
    """
    Result of an individual health check component.

    Attributes
    ----------
    status : CheckStatus
        Status of the check (pass, fail, warn)
    response_ms : int | None
        Response time in milliseconds
    message : str | None
        Optional message or error details
    details : dict[str, Any]
        Additional check-specific details
    """

    status: CheckStatus
    response_ms: int | None = None
    message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary format.

        Returns:
            Dictionary representation of the check.
        """
        result: dict[str, Any] = {"status": self.status.value}
        if self.response_ms is not None:
            result["response_ms"] = self.response_ms
        if self.message is not None:
            result["message"] = self.message
        if self.details:
            result.update(self.details)
        return result


@dataclass
class HealthStatus:
    """
    Complete health status response.

    Attributes
    ----------
    status : OverallStatus
        Overall health status
    timestamp : str
        ISO format timestamp
    version : str
        Application version
    checks : dict[str, ComponentCheck]
        Individual component checks
    """

    status: OverallStatus
    timestamp: str
    version: str
    checks: dict[str, ComponentCheck] = field(default_factory=dict)

    @property
    def is_healthy(self) -> bool:
        """
        Check if overall status is healthy.

        Returns:
            True if status is ready or live.
        """
        return self.status in (OverallStatus.READY, OverallStatus.LIVE)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary format for JSON response.

        Returns:
            Dictionary representation of health status.
        """
        return {
            "status": self.status.value,
            "timestamp": self.timestamp,
            "version": self.version,
            "checks": {name: check.to_dict() for name, check in self.checks.items()},
        }


class HealthChecker:
    """
    Health checker for Kubernetes-compatible probes.

    This class provides methods to check the health of various components
    of the application with appropriate timeouts.

    Examples
    --------
    >>> checker = HealthChecker()
    >>> liveness = await checker.check_liveness()
    >>> readiness = await checker.check_readiness()
    """

    def __init__(self, app: FastAPI, version: str = "1.0.0") -> None:
        """
        Initialize the health checker.

        Args:
            app: FastAPI application instance.
            version: Application version string.
        """
        self.app = app
        self.version = version

    def check_liveness(self) -> HealthStatus:
        """
        Check liveness - basic app responsiveness only.

        This check should not depend on any external services.
        Kubernetes restarts the pod if this fails.

        Returns:
            HealthStatus with LIVE status.

        Examples:
        --------
        >>> status = await checker.check_liveness()
        >>> assert status.status == OverallStatus.LIVE
        """
        return HealthStatus(
            status=OverallStatus.LIVE,
            timestamp=today_str(),
            version=self.version,
            checks={},
        )

    async def check_readiness(self) -> HealthStatus:
        """
        Check readiness - verify all dependencies are available.

        This check validates database, Redis, and other dependencies.
        Kubernetes stops routing traffic if this fails.

        Returns:
            HealthStatus with readiness information.

        Examples:
        --------
        >>> status = await checker.check_readiness()
        >>> if status.is_healthy:
        ...     print("Service is ready for traffic")
        """
        checks: dict[str, ComponentCheck] = {}
        overall_status = OverallStatus.READY

        # Check database
        db_check = await self._check_database()
        checks["database"] = db_check
        if db_check.status == CheckStatus.FAIL:
            overall_status = OverallStatus.NOT_READY

        # Check Redis
        redis_check = await self._check_redis()
        checks["redis"] = redis_check
        if redis_check.status == CheckStatus.FAIL:
            overall_status = OverallStatus.NOT_READY

        # Check disk space
        disk_check = self._check_disk()
        checks["disk"] = disk_check
        if disk_check.status == CheckStatus.FAIL:
            overall_status = OverallStatus.NOT_READY

        return HealthStatus(
            status=overall_status,
            timestamp=datetime.now(UTC).isoformat(),
            version=self.version,
            checks=checks,
        )

    async def check_combined(self) -> HealthStatus:
        """
        Combine liveness and readiness checks for backward compatibility.

        Returns:
            HealthStatus combining liveness and readiness.
        """
        # Start with readiness check
        status = await self.check_readiness()

        # If ready, also consider it live
        if status.is_healthy:
            status.status = OverallStatus.READY

        return status

    async def _check_database(self) -> ComponentCheck:
        """
        Check database connectivity.

        Returns:
            ComponentCheck with database status.
        """

        start = perf_counter()
        try:
            # Try to execute a simple query with timeout
            async with transaction() as session:
                await wait_for(
                    session.execute(text("SELECT 1")),
                    timeout=HEALTH_CHECK_TIMEOUTS["database"],
                )

            elapsed_ms = int((perf_counter() - start) * 1000)
            return ComponentCheck(
                status=CheckStatus.PASS,
                response_ms=elapsed_ms,
            )
        except TimeoutError:
            elapsed_ms = int((perf_counter() - start) * 1000)
            return ComponentCheck(
                status=CheckStatus.FAIL,
                response_ms=elapsed_ms,
                message="Database check timed out",
            )
        except (RuntimeError, ConnectionError) as e:
            elapsed_ms = int((perf_counter() - start) * 1000)
            return ComponentCheck(
                status=CheckStatus.FAIL,
                response_ms=elapsed_ms,
                message=f"Database check failed: {e!s}",
            )

    async def _check_redis(self) -> ComponentCheck:
        """
        Check Redis connectivity.

        Returns:
            ComponentCheck with Redis status.
        """
        start = perf_counter()
        try:
            # Try to ping Redis with timeout - request will be None in health check context
            cache_manager = self.app.state.cache_manager
            if cache_manager.is_redis_available:
                await wait_for(
                    cache_manager.redis_client.ping(),
                    timeout=HEALTH_CHECK_TIMEOUTS["redis"],
                )
                elapsed_ms = int((perf_counter() - start) * 1000)
                return ComponentCheck(
                    status=CheckStatus.PASS,
                    response_ms=elapsed_ms,
                )
            else:
                # Redis not configured or using in-memory fallback
                elapsed_ms = int((perf_counter() - start) * 1000)
                return ComponentCheck(
                    status=CheckStatus.WARN,
                    response_ms=elapsed_ms,
                    message="Redis not available, using in-memory fallback",
                )
        except TimeoutError:
            elapsed_ms = int((perf_counter() - start) * 1000)
            return ComponentCheck(
                status=CheckStatus.FAIL,
                response_ms=elapsed_ms,
                message="Redis check timed out",
            )
        except Exception as e:  # noqa: BLE001
            elapsed_ms = int((perf_counter() - start) * 1000)
            return ComponentCheck(
                status=CheckStatus.FAIL,
                response_ms=elapsed_ms,
                message=f"Redis check failed: {e!s}",
            )

    def _check_disk(self) -> ComponentCheck:
        """
        Check disk space usage.

        Returns:
            ComponentCheck with disk status.
        """

        try:
            disk = disk_usage("/")
            usage_percent = disk.percent

            # Consider >90% disk usage as warning, >95% as fail
            if usage_percent > 95:
                status = CheckStatus.FAIL
            elif usage_percent > 90:
                status = CheckStatus.WARN
            else:
                status = CheckStatus.PASS

            return ComponentCheck(
                status=status,
                details={"usage_percent": usage_percent},
            )
        except Exception as e:  # noqa: BLE001
            return ComponentCheck(
                status=CheckStatus.WARN,
                message=f"Could not check disk: {e!s}",
            )
