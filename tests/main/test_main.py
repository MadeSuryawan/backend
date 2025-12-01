import uuid

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
    # Validate response matches HealthCheckResponse schema
    assert "status" in data
    assert "backend" in data
    assert "statistics" in data
    # Validate statistics structure
    stats = data["statistics"]
    assert "hits" in stats
    assert "misses" in stats
    assert "sets" in stats
    assert "hit_rate" in stats


@mark.asyncio
async def test_metrics_rate_limit(client: AsyncClient) -> None:
    unique_key = str(uuid.uuid4())
    headers = {"X-API-Key": unique_key}

    # Hit the endpoint 5 times (allowed)
    for _ in range(5):
        response = await client.get("/metrics", headers=headers)
        assert response.status_code == 200

    # The 6th request should be rate limited
    response = await client.get("/metrics", headers=headers)
    assert response.status_code == 429
    assert "Rate limit exceeded" in response.text
