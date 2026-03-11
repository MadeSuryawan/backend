from uuid import uuid4

from httpx import AsyncClient
from pytest import mark


@mark.asyncio
async def test_root_endpoint(client: AsyncClient) -> None:
    """Test root endpoint."""
    response = await client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()


@mark.asyncio
async def test_health_check(client: AsyncClient) -> None:
    """Test health check endpoint."""
    response = await client.get("/health")
    # Health check often relies on the global manager or internal logic,
    # but since we overrode the dependency for the client, it should reflect that.
    assert response.status_code in [200, 503]
    data = response.json()

    # Validate top-level response structure
    assert "version" in data
    assert "status" in data
    assert "timestamp" in data
    assert "services" in data
    assert "cache" in data

    # Validate services structure
    services = data["services"]
    assert "ai_client" in services
    assert "email_client" in services
    assert "ai_circuit_breaker" in services
    assert "email_circuit_breaker" in services

    # Validate circuit breaker structure
    ai_cb = services["ai_circuit_breaker"]
    assert "name" in ai_cb
    assert "state" in ai_cb
    assert "failure_count" in ai_cb

    # Validate cache structure
    cache = data["cache"]
    assert "backend" in cache
    assert "statistics" in cache
    assert "status" in cache

    # Validate statistics structure
    stats = cache["statistics"]
    assert "hits" in stats
    assert "misses" in stats
    assert "sets" in stats
    assert "hit_rate" in stats


@mark.asyncio
async def test_health_check_requires_admin(unauthenticated_client: AsyncClient) -> None:
    """Legacy health endpoint should require admin authentication."""
    response = await unauthenticated_client.get("/health")
    assert response.status_code == 401


@mark.asyncio
async def test_metrics_rate_limit(client: AsyncClient) -> None:
    unique_key = str(uuid4())
    headers = {"X-API-Key": unique_key}

    # Hit the endpoint 5 times (allowed)
    for _ in range(5):
        response = await client.get("/metrics/legacy", headers=headers)
        assert response.status_code == 200

    # The 6th request should be rate limited
    response = await client.get("/metrics/legacy", headers=headers)
    assert response.status_code == 429
    assert "Rate limit exceeded" in response.text


@mark.asyncio
async def test_metrics_legacy_requires_admin(unauthenticated_client: AsyncClient) -> None:
    """Legacy metrics endpoint should require admin authentication."""
    response = await unauthenticated_client.get(
        "/metrics/legacy",
        headers={"X-API-Key": str(uuid4())},
    )
    assert response.status_code == 401
