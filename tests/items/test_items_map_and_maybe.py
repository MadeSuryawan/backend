import pytest
from httpx import AsyncClient


class TestItemsMapAndMaybe:
    @pytest.mark.asyncio
    async def test_map_and_maybe_flow(self, client: AsyncClient) -> None:
        cleared = await client.delete("/items/clear-all")
        assert cleared.status_code == 200
        item1 = {"id": 1, "name": "A", "price": 9.99}
        item2 = {"id": 2, "name": "B", "price": 19.99}

        r1 = await client.post("/items/", json=item1)
        assert r1.status_code == 200
        r2 = await client.post("/items/", json=item2)
        assert r2.status_code == 200

        m1 = await client.get("/items/map-items")
        assert m1.status_code == 200
        mapping1 = m1.json()
        assert "A" in mapping1 and mapping1["A"]["id"] == 1
        assert "B" in mapping1 and mapping1["B"]["id"] == 2

        m2 = await client.get("/items/map-items")
        assert m2.status_code == 200
        assert m2.json() == mapping1

        ex1 = await client.get("/items/maybe-item/1")
        assert ex1.status_code == 200
        assert ex1.json()["id"] == 1

        miss = await client.get("/items/maybe-item/99")
        assert miss.status_code == 200
        assert miss.json() is None

        update_payload = {"name": "A-New", "price": 10.5}
        up = await client.patch("/items/update-item/1", json=update_payload)
        assert up.status_code == 200
        assert up.json()["name"] == "A-New"

        m3 = await client.get("/items/map-items")
        assert m3.status_code == 200
        mapping3 = m3.json()
        assert "A-New" in mapping3 and mapping3["A-New"]["id"] == 1

        d = await client.delete("/items/delete-item/2")
        assert d.status_code == 200

        m4 = await client.get("/items/map-items")
        assert m4.status_code == 200
        mapping4 = m4.json()
        assert "B" not in mapping4

        ex1b = await client.get("/items/maybe-item/1")
        assert ex1b.status_code == 200
        assert ex1b.json()["name"] == "A-New"

        ex2b = await client.get("/items/maybe-item/2")
        assert ex2b.status_code == 200
        assert ex2b.json() is None
