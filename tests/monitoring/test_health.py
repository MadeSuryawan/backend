"""Tests for health check functionality."""

from __future__ import annotations

import pytest

from app.monitoring.health import (
    HealthStatus,
    LivenessResponse,
    perform_liveness_check,
)


@pytest.mark.asyncio
async def test_liveness_check_returns_pass() -> None:
    """Liveness check should always return pass status."""
    response = await perform_liveness_check()
    assert isinstance(response, LivenessResponse)
    assert response.status == HealthStatus.PASS


@pytest.mark.asyncio
async def test_health_live_endpoint(client) -> None:
    """Test /health/live endpoint returns 200."""
    response = await client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pass"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_ready_endpoint(client) -> None:
    """Test /health/ready endpoint returns proper structure."""
    response = await client.get("/health/ready")
    # May return 200 or 503 depending on database availability
    assert response.status_code in [200, 503]
    data = response.json()
    assert "status" in data
    assert "checks" in data
    assert "timestamp" in data


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_status_values(self) -> None:
        """Health status values should be correct."""
        assert HealthStatus.PASS.value == "pass"
        assert HealthStatus.WARN.value == "warn"
        assert HealthStatus.FAIL.value == "fail"
