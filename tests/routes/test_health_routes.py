from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.dependencies.dependencies import get_email_client, get_health_checker, is_admin
from app.errors.email import EmailServiceError
from app.main import app
from app.models import UserDB
from app.monitoring.health import CheckStatus, ComponentCheck, HealthStatus, OverallStatus
from app.routes import health as health_routes


class DummyHealthChecker:
    def __init__(
        self,
        *,
        live: HealthStatus | None = None,
        ready: HealthStatus | None = None,
    ) -> None:
        self._live = live
        self._ready = ready

    def check_liveness(self) -> HealthStatus:
        assert self._live is not None
        return self._live

    async def check_readiness(self) -> HealthStatus:
        assert self._ready is not None
        return self._ready


class DummyCacheManager:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    async def health_check(self) -> dict[str, Any]:
        return self._payload


class AvailableEmailClient:
    service = object()


class MissingEmailClient:
    @property
    def service(self) -> object:
        raise EmailServiceError()


class DummyCircuitBreaker:
    def __init__(self, name: str) -> None:
        self._name = name

    def get_state(self) -> dict[str, Any]:
        return make_circuit_state(self._name)


class DummyMetricsManager:
    def get_metrics(self) -> dict[str, int]:
        return {"requests": 12}


def make_health_status(status: OverallStatus, check_status: CheckStatus) -> HealthStatus:
    return HealthStatus(
        status=status,
        timestamp="2026-03-11T00:00:00Z",
        version="1.0.0",
        checks={"database": ComponentCheck(status=check_status, response_ms=12)},
    )


def make_cache_health() -> dict[str, Any]:
    return {
        "backend": "memory",
        "status": "healthy",
        "info": {"mode": "in-memory"},
        "statistics": {
            "hits": 1,
            "misses": 2,
            "sets": 3,
            "deletes": 4,
            "evictions": 0,
            "errors": 0,
            "total_bytes_written": 10,
            "total_bytes_read": 20,
            "hit_rate": "33.3%",
            "total_requests": 3,
            "created_at": "2026-03-11T00:00:00Z",
            "last_updated_at": "2026-03-11T00:00:00Z",
        },
    }


def make_circuit_state(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "state": "closed",
        "failure_count": 0,
        "failure_threshold": 5,
        "last_failure_time": None,
        "time_until_reset": 0.0,
        "success_threshold": 2,
        "half_open_successes": 0,
    }


@pytest.fixture(autouse=True)
def clear_health_test_overrides() -> Generator:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_liveness_probe_returns_live_payload(client: AsyncClient) -> None:
    app.dependency_overrides[get_health_checker] = lambda: DummyHealthChecker(
        live=make_health_status(OverallStatus.LIVE, CheckStatus.PASS),
    )

    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "live"


@pytest.mark.asyncio
async def test_readiness_probe_returns_503_when_not_ready(client: AsyncClient) -> None:
    app.dependency_overrides[get_health_checker] = lambda: DummyHealthChecker(
        ready=make_health_status(OverallStatus.NOT_READY, CheckStatus.FAIL),
    )

    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["database"]["status"] == "fail"


@pytest.mark.asyncio
async def test_health_check_maps_unavailable_clients(
    client: AsyncClient,
    admin_user: UserDB,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def admin_override() -> UserDB:
        return admin_user

    def email_override() -> MissingEmailClient:
        return MissingEmailClient()

    app.dependency_overrides[is_admin] = admin_override
    app.dependency_overrides[get_health_checker] = lambda: DummyHealthChecker(
        ready=make_health_status(OverallStatus.READY, CheckStatus.PASS),
    )
    app.dependency_overrides[get_email_client] = email_override
    monkeypatch.setattr(app.state, "ai_client", None, raising=False)
    monkeypatch.setattr(
        app.state,
        "cache_manager",
        DummyCacheManager(make_cache_health()),
        raising=False,
    )
    monkeypatch.setattr(health_routes, "today_str", lambda: "2026-03-11")
    monkeypatch.setattr(health_routes, "ai_circuit_breaker", DummyCircuitBreaker("ai"))
    monkeypatch.setattr(health_routes, "email_circuit_breaker", DummyCircuitBreaker("email"))

    response = await client.get("/health")

    data = response.json()
    assert response.status_code == 200
    assert data["services"]["ai_client"] == "not_initialized"
    assert data["services"]["email_client"] == "not_configured"
    assert data["cache"]["backend"] == "memory"


@pytest.mark.asyncio
async def test_health_check_reports_initialized_services(
    client: AsyncClient,
    admin_user: UserDB,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def admin_override() -> UserDB:
        return admin_user

    def email_override() -> AvailableEmailClient:
        return AvailableEmailClient()

    app.dependency_overrides[is_admin] = admin_override
    app.dependency_overrides[get_health_checker] = lambda: DummyHealthChecker(
        ready=make_health_status(OverallStatus.READY, CheckStatus.PASS),
    )
    app.dependency_overrides[get_email_client] = email_override
    monkeypatch.setattr(app.state, "ai_client", object(), raising=False)
    monkeypatch.setattr(
        app.state,
        "cache_manager",
        DummyCacheManager(make_cache_health()),
        raising=False,
    )
    monkeypatch.setattr(health_routes, "today_str", lambda: "2026-03-11")
    monkeypatch.setattr(health_routes, "ai_circuit_breaker", DummyCircuitBreaker("ai"))
    monkeypatch.setattr(health_routes, "email_circuit_breaker", DummyCircuitBreaker("email"))

    response = await client.get("/health")

    services = response.json()["services"]
    assert response.status_code == 200
    assert services["ai_client"] == "initialized"
    assert services["email_client"] == "available"


@pytest.mark.asyncio
async def test_metrics_legacy_returns_patched_metrics_payload(
    client: AsyncClient,
    admin_user: UserDB,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def admin_override() -> UserDB:
        return admin_user

    app.dependency_overrides[is_admin] = admin_override
    system_metrics = {"cpu": 0.5, "mem": 0.7}
    monkeypatch.setattr(health_routes, "today_str", lambda: "2026-03-11")
    monkeypatch.setattr(health_routes, "metrics_manager", DummyMetricsManager())
    monkeypatch.setattr(
        health_routes,
        "get_system_metrics",
        AsyncMock(return_value=system_metrics),
    )

    response = await client.get("/metrics/legacy", headers={"X-API-Key": "health-tests"})

    assert response.status_code == 200
    assert response.json() == {
        "timestamp": "2026-03-11",
        "api_metrics": {"requests": 12},
        "system_metrics": system_metrics,
    }
