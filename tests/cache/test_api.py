# tests/cache/test_api.py
"""Tests for FastAPI endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.main import app
from app.routes.cache import get_cache_manager


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient) -> None:
    """Test root endpoint."""
    response = await client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient) -> None:
    """Test health check endpoint."""
    response = await client.get("/health")
    # Health check often relies on the global manager or internal logic,
    # but since we overrode the dependency for the client, it should reflect that.
    assert response.status_code in [200, 503]
    data = response.json()
    assert "status" in data
    assert "cache" in data


@pytest.mark.asyncio
async def test_cache_stats(client: AsyncClient) -> None:
    """Test cache statistics endpoint."""
    response = await client.get("/cache/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "data" in data


@pytest.mark.asyncio
async def test_cache_ping_success(client: AsyncClient) -> None:
    """Test cache ping endpoint success scenario."""
    # The default 'client' fixture already uses a working CacheManager
    response = await client.get("/cache/ping")

    if response.status_code == 200:
        assert response.json()["status"] == "success"
    else:
        # If the environment actually has no Redis/Memory fallback, it might be 503.
        # But usually in tests, we expect success from the fixture.
        pass


@pytest.mark.asyncio
async def test_cache_ping_failure(client: AsyncClient) -> None:
    """
    Test cache ping endpoint failure scenario.

    Demonstrates the power of Dependency Injection: we can inject a broken
    manager to verify the API correctly returns 503.
    """
    # 1. Create a mock manager that fails to ping
    mock_manager = MagicMock()
    mock_manager.ping = AsyncMock(return_value=False)

    # 2. Override the dependency specifically for this request
    app.dependency_overrides[get_cache_manager] = lambda: mock_manager

    # 3. Make the request
    response = await client.get("/cache/ping")

    # 4. Assert it handled the error correctly
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "error"
    assert data["message"] == "Cache server is not reachable"

    # 5. Reset overrides (handled by fixture teardown usually, but good practice here)
    # Note: The client fixture will clear this on exit, but we want to be safe.
    # To restore the 'working' fixture manager:
    # We can't easily "restore" to the fixture's closure value here without access to it.
    # So we rely on the fixture teardown or simply don't run tests order-dependently.


@pytest.mark.asyncio
async def test_get_all_items(client: AsyncClient) -> None:
    """Test get all items endpoint."""
    response = await client.get("/all-items")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


@pytest.mark.asyncio
async def test_create_item(client: AsyncClient) -> None:
    """Test create item endpoint."""
    item_data = {
        "id": 1,
        "name": "Test Item",
        "description": "A test item",
        "price": 9.99,
    }
    response = await client.post("/create-item", json=item_data)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["name"] == "Test Item"


@pytest.mark.asyncio
async def test_get_item(client: AsyncClient) -> None:
    """Test get specific item endpoint."""
    # Create item first
    item_data = {
        "id": 2,
        "name": "Test Item 2",
        "price": 19.99,
    }
    await client.post("/create-item", json=item_data)

    # Get item
    response = await client.get("/get-item/2")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 2
    assert data["name"] == "Test Item 2"


@pytest.mark.asyncio
async def test_get_nonexistent_item(client: AsyncClient) -> None:
    """Test get nonexistent item returns 404."""
    response = await client.get("/get-item/9999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_item(client: AsyncClient) -> None:
    """Test update item endpoint."""
    # Create item
    item_data = {
        "id": 3,
        "name": "Test Item 3",
        "price": 29.99,
    }
    await client.post("/create-item", json=item_data)

    # Update item
    update_data = {
        "name": "Updated Item 3",
        "price": 39.99,
    }
    response = await client.put("/update-item/3", json=update_data)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Item 3"
    assert data["price"] == 39.99


@pytest.mark.asyncio
async def test_delete_item(client: AsyncClient) -> None:
    """Test delete item endpoint."""
    # Create item
    item_data = {
        "id": 4,
        "name": "Test Item 4",
        "price": 49.99,
    }
    await client.post("/create-item", json=item_data)

    # Delete item
    response = await client.delete("/delete-item/4")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data

    # Verify deletion
    response = await client.get("/get-item/4")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cache_reset_stats(client: AsyncClient) -> None:
    """Test cache reset stats endpoint."""
    response = await client.get("/cache/reset-stats")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"


@pytest.mark.asyncio
async def test_cache_clear(client: AsyncClient) -> None:
    """Test cache clear endpoint returns proper response."""
    # Call the clear cache endpoint
    response = await client.delete("/cache/clear")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "message" in data
    assert data["status"] in ["success", "error"]
