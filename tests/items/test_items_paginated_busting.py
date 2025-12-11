import pytest
from httpx import AsyncClient


class TestItemsPaginatedBusting:
    @pytest.mark.asyncio
    async def test_bust_paginated_page(self, client: AsyncClient) -> None:
        existing = await client.get("/items/raw-items")
        if existing.status_code == 200:
            for d in existing.json():
                await client.delete(f"/items/delete-item/{d['id']}")

        items = [
            {"id": 1, "name": "A", "price": 9.99},
            {"id": 2, "name": "B", "price": 19.99},
            {"id": 3, "name": "C", "price": 29.99},
        ]
        for it in items:
            r = await client.post("/items/", json=it)
            assert r.status_code == 200

        p1 = await client.get("/items/paginated", params={"page": 1, "page_size": 2})
        assert p1.status_code == 200
        data1 = p1.json()
        assert {i["name"] for i in data1["items"]} == {"A", "B"}

        up = await client.put("/items/update-item/1", json={"name": "A-Edit"})
        assert up.status_code == 200

        # Without busting, cached page may still have old name
        p1_cached = await client.get("/items/paginated", params={"page": 1, "page_size": 2})
        assert p1_cached.status_code == 200
        names_cached = {i["name"] for i in p1_cached.json()["items"]}
        assert names_cached == {"A", "B"}

        # Bust the specific paginated page cache
        bust = await client.post("/items/bust-paginated", params={"page": 1, "page_size": 2})
        assert bust.status_code == 200

        # Now it should reflect updated name
        p1_new = await client.get("/items/paginated", params={"page": 1, "page_size": 2})
        assert p1_new.status_code == 200
        names_new = {i["name"] for i in p1_new.json()["items"]}
        assert names_new == {"A-Edit", "B"}

        # Bust all pages for given page_size
        bust_all = await client.post("/items/bust-paginated-all", params={"page_size": 2})
        assert bust_all.status_code == 200

        # Verify both pages reflect the latest data
        p1_after = await client.get("/items/paginated", params={"page": 1, "page_size": 2})
        p2_after = await client.get("/items/paginated", params={"page": 2, "page_size": 2})
        assert {i["name"] for i in p1_after.json()["items"]} == {"A-Edit", "B"}
        assert {i["name"] for i in p2_after.json()["items"]} == {"C"}
