import pytest
from httpx import AsyncClient


class TestItemsPaginatedMultiBusting:
    @pytest.mark.asyncio
    async def test_bust_multiple_page_sizes(self, client: AsyncClient) -> None:
        cleared = await client.delete("/items/clear-all")
        assert cleared.status_code == 200

        items = [
            {"id": 1, "name": "A", "price": 9.99},
            {"id": 2, "name": "B", "price": 19.99},
            {"id": 3, "name": "C", "price": 29.99},
            {"id": 4, "name": "D", "price": 39.99},
        ]
        for it in items:
            r = await client.post("/items/", json=it)
            assert r.status_code == 200

        p1_s1 = await client.get("/items/paginated", params={"page": 1, "page_size": 1})
        p1_s2 = await client.get("/items/paginated", params={"page": 1, "page_size": 2})
        assert p1_s1.status_code == 200 and p1_s2.status_code == 200

        up = await client.put("/items/update-item/1", json={"name": "A-Edit"})
        assert up.status_code == 200

        p1_s1_cached = await client.get("/items/paginated", params={"page": 1, "page_size": 1})
        assert {i["name"] for i in p1_s1_cached.json()["items"]} == {"A"}

        bust_multi = await client.post(
            "/items/bust-paginated-multi",
            params=[("page_sizes", 1), ("page_sizes", 2)],
        )
        assert bust_multi.status_code == 200

        p1_s1_new = await client.get("/items/paginated", params={"page": 1, "page_size": 1})
        p1_s2_new = await client.get("/items/paginated", params={"page": 1, "page_size": 2})
        assert {i["name"] for i in p1_s1_new.json()["items"]} == {"A-Edit"}
        assert {i["name"] for i in p1_s2_new.json()["items"]} == {"A-Edit", "B"}
