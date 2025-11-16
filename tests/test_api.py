"""Tests for FastAPI endpoints."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """Create async HTTP client for testing."""
    async with AsyncClient(
        base_url="http://test",
        transport=ASGITransport(app=app),
    ) as ac:
        yield ac


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
async def test_cache_ping(client: AsyncClient) -> None:
    """Test cache ping endpoint."""
    response = await client.get("/cache/ping")
    # May return 503 if Redis not running, but request should succeed
    assert response.status_code in [200, 503]


@pytest.mark.asyncio
async def test_get_all_items(client: AsyncClient) -> None:
    """Test get all items endpoint."""
    response = await client.get("/items")
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
    response = await client.post("/items", json=item_data)
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
    await client.post("/items", json=item_data)

    # Get item
    response = await client.get("/items/2")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 2
    assert data["name"] == "Test Item 2"


@pytest.mark.asyncio
async def test_get_nonexistent_item(client: AsyncClient) -> None:
    """Test get nonexistent item returns 404."""
    response = await client.get("/items/9999")
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
    await client.post("/items", json=item_data)

    # Update item
    update_data = {
        "name": "Updated Item 3",
        "price": 39.99,
    }
    response = await client.put("/items/3", json=update_data)
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
    await client.post("/items", json=item_data)

    # Delete item
    response = await client.delete("/items/4")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data

    # Verify deletion
    response = await client.get("/items/4")
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
    # Should get a 200 response (endpoint may succeed or fail gracefully)
    assert response.status_code == 200
    data = response.json()
    # Check that we get proper response structure
    assert "status" in data
    assert "message" in data
    # Should be either success or error
    assert data["status"] in ["success", "error"]
