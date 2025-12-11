import pytest
from httpx import AsyncClient


class TestItemsPagination:
    @pytest.mark.asyncio
    async def test_paginated_flow(self, client: AsyncClient) -> None:
        cleared = await client.delete("/items/clear-all")
        assert cleared.status_code == 200
        after_clear = await client.get("/items/raw-items", params={"refresh": True})
        assert after_clear.status_code == 200
        assert len(after_clear.json()) == 0

        items = [
            {"id": 1, "name": "A", "price": 9.99},
            {"id": 2, "name": "B", "price": 19.99},
            {"id": 3, "name": "C", "price": 29.99},
        ]
        for it in items:
            r = await client.post("/items/", json=it)
            assert r.status_code == 200
        after_create = await client.get("/items/raw-items", params={"refresh": True})
        assert after_create.status_code == 200
        expected_total = len(after_create.json())

        p1 = await client.get("/items/paginated", params={"page": 1, "page_size": 2})
        assert p1.status_code == 200
        data1 = p1.json()
        assert data1["total"] == expected_total
        assert data1["page"] == 1
        assert data1["page_size"] == 2
        assert data1["pages"] == (expected_total + 2 - 1) // 2
        assert len(data1["items"]) == 2
        assert {i["id"] for i in data1["items"]} == {1, 2}

        p1b = await client.get("/items/paginated", params={"page": 1, "page_size": 2})
        assert p1b.status_code == 200
        assert p1b.json() == data1

        p2 = await client.get("/items/paginated", params={"page": 2, "page_size": 2})
        assert p2.status_code == 200
        data2 = p2.json()
        assert len(data2["items"]) == max(expected_total - 2, 0)
        assert {i["id"] for i in data2["items"]} == ({3} if expected_total >= 3 else set())
