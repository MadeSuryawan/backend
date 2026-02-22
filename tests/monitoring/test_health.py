"""Tests for monitoring health module."""

import pytest
from fastapi import FastAPI

from app.monitoring.health import (
    CheckStatus,
    ComponentCheck,
    HealthChecker,
    HealthStatus,
    OverallStatus,
)


class TestComponentCheck:
    """Tests for ComponentCheck dataclass."""

    def test_to_dict_with_all_fields(self) -> None:
        """Test to_dict with all fields populated."""
        check = ComponentCheck(
            status=CheckStatus.PASS,
            response_ms=15,
            message="OK",
            details={"usage_percent": 45},
        )
        result = check.to_dict()
        assert result["status"] == "pass"
        assert result["response_ms"] == 15
        assert result["message"] == "OK"
        assert result["usage_percent"] == 45

    def test_to_dict_with_minimal_fields(self) -> None:
        """Test to_dict with only status field."""
        check = ComponentCheck(status=CheckStatus.FAIL)
        result = check.to_dict()
        assert result == {"status": "fail"}


class TestHealthStatus:
    """Tests for HealthStatus dataclass."""

    def test_is_healthy_ready(self) -> None:
        """Test that READY status is healthy."""
        status = HealthStatus(
            status=OverallStatus.READY,
            timestamp="2025-01-01T00:00:00Z",
            version="1.0.0",
        )
        assert status.is_healthy is True

    def test_is_healthy_live(self) -> None:
        """Test that LIVE status is healthy."""
        status = HealthStatus(
            status=OverallStatus.LIVE,
            timestamp="2025-01-01T00:00:00Z",
            version="1.0.0",
        )
        assert status.is_healthy is True

    def test_is_not_healthy_not_ready(self) -> None:
        """Test that NOT_READY status is not healthy."""
        status = HealthStatus(
            status=OverallStatus.NOT_READY,
            timestamp="2025-01-01T00:00:00Z",
            version="1.0.0",
        )
        assert status.is_healthy is False

    def test_to_dict_structure(self) -> None:
        """Test to_dict output structure."""
        checks = {
            "database": ComponentCheck(status=CheckStatus.PASS, response_ms=10),
        }
        status = HealthStatus(
            status=OverallStatus.READY,
            timestamp="2025-01-01T00:00:00Z",
            version="1.0.0",
            checks=checks,
        )
        result = status.to_dict()
        assert result["status"] == "ready"
        assert result["timestamp"] == "2025-01-01T00:00:00Z"
        assert result["version"] == "1.0.0"
        assert "checks" in result
        assert result["checks"]["database"]["status"] == "pass"


class TestHealthChecker:
    """Tests for HealthChecker class."""

    @pytest.mark.asyncio
    async def test_check_liveness_returns_live(self) -> None:
        """Test that liveness check returns LIVE status."""

        checker = HealthChecker(app=FastAPI(), version="1.0.0")
        result = checker.check_liveness()
        assert result.status == OverallStatus.LIVE
        assert result.version == "1.0.0"
        assert result.checks == {}

    @pytest.mark.asyncio
    async def test_check_liveness_has_timestamp(self) -> None:
        """Test that liveness check includes timestamp."""

        checker = HealthChecker(app=FastAPI())
        result = checker.check_liveness()
        assert result.timestamp is not None
        assert len(result.timestamp) > 0

    @pytest.mark.asyncio
    async def test_check_readiness_returns_status(self) -> None:
        """Test that readiness check returns a status."""

        checker = HealthChecker(app=FastAPI())
        result = await checker.check_readiness()
        assert result.status in (OverallStatus.READY, OverallStatus.NOT_READY)
        assert "database" in result.checks
        assert "redis" in result.checks
        assert "disk" in result.checks

    @pytest.mark.asyncio
    async def test_check_readiness_checks_have_status(self) -> None:
        """Test that all checks have a status field."""

        checker = HealthChecker(app=FastAPI())
        result = await checker.check_readiness()
        for _check_name, check in result.checks.items():
            assert check.status in (CheckStatus.PASS, CheckStatus.FAIL, CheckStatus.WARN)

    @pytest.mark.asyncio
    async def test_check_combined_returns_status(self) -> None:
        """Test that combined check returns a status."""

        checker = HealthChecker(app=FastAPI())
        result = await checker.check_combined()
        assert isinstance(result.status, OverallStatus)


class TestCheckStatus:
    """Tests for CheckStatus enum."""

    def test_values(self) -> None:
        """Test that enum has expected values."""
        assert CheckStatus.PASS.value == "pass"
        assert CheckStatus.FAIL.value == "fail"
        assert CheckStatus.WARN.value == "warn"


class TestOverallStatus:
    """Tests for OverallStatus enum."""

    def test_values(self) -> None:
        """Test that enum has expected values."""
        assert OverallStatus.READY.value == "ready"
        assert OverallStatus.NOT_READY.value == "not_ready"
        assert OverallStatus.ERROR.value == "error"
        assert OverallStatus.LIVE.value == "live"
