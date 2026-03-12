from collections.abc import AsyncGenerator, Generator
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.managers.rate_limiter import limiter
from app.routes.items import items_db
from app.schemas import Item


def async_mock_attr(mock: MagicMock, name: str) -> AsyncMock:
    return cast(AsyncMock, getattr(mock, name))


@pytest.fixture(autouse=True)
def reset_items_db() -> Generator[None]:
    items_db.clear()
    yield
    items_db.clear()


@pytest.fixture
def mock_cache_manager() -> Generator[MagicMock]:
    mock = MagicMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)

    had_cache_manager = hasattr(app.state, "cache_manager")
    original_cache_manager = getattr(app.state, "cache_manager", None)
    app.state.cache_manager = mock

    yield mock

    if had_cache_manager:
        app.state.cache_manager = original_cache_manager
    elif hasattr(app.state, "cache_manager"):
        delattr(app.state, "cache_manager")


@pytest.fixture
async def client(mock_cache_manager: MagicMock) -> AsyncGenerator[AsyncClient]:
    assert mock_cache_manager is not None
    limiter.enabled = False
    async with AsyncClient(base_url="http://test", transport=ASGITransport(app=app)) as ac:
        yield ac
    limiter.enabled = True


@pytest.mark.asyncio
async def test_create_item_sets_write_through_cache_and_busts_collections(
    client: AsyncClient,
    mock_cache_manager: MagicMock,
) -> None:
    response = await client.post(
        "/items/",
        json={"id": 11, "name": "Widget", "description": "cache me", "price": 19.5},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Widget"

    async_mock_attr(mock_cache_manager, "set").assert_awaited_once_with(
        "item_11",
        {"id": 11, "name": "Widget", "description": "cache me", "price": 19.5},
        ttl=3600,
        namespace="items",
    )
    async_mock_attr(mock_cache_manager, "delete").assert_awaited_once_with(
        "get_all_items",
        "get_raw_items",
        "get_map_items",
        "get_dict_list_items",
        "get_tuple_items",
        namespace="items",
    )


@pytest.mark.asyncio
async def test_missing_item_paths_return_404_without_busting_mutation_cache(
    client: AsyncClient,
    mock_cache_manager: MagicMock,
) -> None:
    get_response = await client.get("/items/get-item/999")
    update_response = await client.patch("/items/update-item/999", json={"name": "ghost"})
    delete_response = await client.delete("/items/delete-item/999")

    assert get_response.status_code == 404
    assert update_response.status_code == 404
    assert delete_response.status_code == 404
    assert get_response.json()["detail"] == "Item not found"
    assert update_response.json()["detail"] == "Item not found"
    assert delete_response.json()["detail"] == "Item not found"

    async_mock_attr(mock_cache_manager, "get").assert_awaited_once_with("item_999", "items")
    async_mock_attr(mock_cache_manager, "delete").assert_not_awaited()
    async_mock_attr(mock_cache_manager, "set").assert_not_awaited()


@pytest.mark.asyncio
async def test_bust_paginated_all_deletes_every_page_for_size(
    client: AsyncClient,
    mock_cache_manager: MagicMock,
) -> None:
    items_db.update(
        {
            1: Item(id=1, name="A", price=9.99),
            2: Item(id=2, name="B", price=19.99),
            3: Item(id=3, name="C", price=29.99),
        },
    )

    response = await client.post("/items/bust-paginated-all", params={"page_size": 2})

    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    async_mock_attr(mock_cache_manager, "delete").assert_awaited_once_with(
        "get_paginated_items_1_2",
        "get_paginated_items_2_2",
        namespace="items",
    )


@pytest.mark.asyncio
async def test_bust_paginated_multi_skips_invalid_sizes(
    client: AsyncClient,
    mock_cache_manager: MagicMock,
) -> None:
    items_db.update(
        {
            1: Item(id=1, name="A", price=9.99),
            2: Item(id=2, name="B", price=19.99),
            3: Item(id=3, name="C", price=29.99),
        },
    )

    response = await client.post(
        "/items/bust-paginated-multi",
        params=[("page_sizes", 0), ("page_sizes", 2), ("page_sizes", 101), ("page_sizes", 3)],
    )

    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    async_mock_attr(mock_cache_manager, "delete").assert_awaited_once_with(
        "get_paginated_items_1_2",
        "get_paginated_items_2_2",
        "get_paginated_items_1_3",
        namespace="items",
    )


@pytest.mark.asyncio
async def test_clear_all_items_clears_store_and_busts_common_keys(
    client: AsyncClient,
    mock_cache_manager: MagicMock,
) -> None:
    items_db.update({1: Item(id=1, name="A", price=9.99), 2: Item(id=2, name="B", price=19.99)})

    response = await client.delete("/items/clear-all")

    assert response.status_code == 200
    assert response.json() == {"status": "cleared"}
    assert items_db == {}

    delete_await = async_mock_attr(mock_cache_manager, "delete").await_args
    assert delete_await is not None
    assert delete_await.args[:5] == (
        "get_all_items",
        "get_raw_items",
        "get_map_items",
        "get_dict_list_items",
        "get_tuple_items",
    )
    assert len(delete_await.args) == 155
    assert "get_paginated_items_1_1" in delete_await.args
    assert "get_paginated_items_50_10" in delete_await.args
    assert delete_await.kwargs == {"namespace": "items"}
