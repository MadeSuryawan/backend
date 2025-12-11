
import pytest
from httpx import AsyncClient


class TestItemsRawEndpoint:
    @pytest.mark.asyncio
    async def test_raw_items_flow(self, client: AsyncClient) -> None:
        # Create two items
        cleared = await client.delete("/items/clear-all")
        assert cleared.status_code == 200
        item1 = {"id": 1, "name": "A", "price": 9.99}
        item2 = {"id": 2, "name": "B", "price": 19.99}

        r1 = await client.post("/items/", json=item1)
        assert r1.status_code == 200

        r2 = await client.post("/items/", json=item2)
        assert r2.status_code == 200

        # Read raw list
        g1 = await client.get("/items/raw-items")
        assert g1.status_code == 200
        data1 = g1.json()
        assert isinstance(data1, list)
        assert any(d["id"] == 1 and d["name"] == "A" for d in data1)
        assert any(d["id"] == 2 and d["name"] == "B" for d in data1)

        # Call again to exercise caching hit path
        g2 = await client.get("/items/raw-items")
        assert g2.status_code == 200
        assert g2.json() == data1

        # Update item 1, verify cache busting reflects update
        update_payload = {"name": "A-Updated", "price": 11.5}
        u = await client.put("/items/update-item/1", json=update_payload)
        assert u.status_code == 200
        assert u.json()["name"] == "A-Updated"

        g3 = await client.get("/items/raw-items")
        assert g3.status_code == 200
        data3 = g3.json()
        assert any(d["id"] == 1 and d["name"] == "A-Updated" for d in data3)

        # Delete item 2, verify cache busting reflects deletion
        d = await client.delete("/items/delete-item/2")
        assert d.status_code == 200

        g4 = await client.get("/items/raw-items")
        assert g4.status_code == 200
        data4 = g4.json()
        assert all(d["id"] != 2 for d in data4)
