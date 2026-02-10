import pytest
from httpx import AsyncClient


class TestItemsNestedContainers:
    @pytest.mark.asyncio
    async def test_dict_list_and_tuple_flow(self, client: AsyncClient) -> None:
        cleared = await client.delete("/items/clear-all")
        assert cleared.status_code == 200
        item1 = {"id": 1, "name": "A", "price": 9.99}
        item2 = {"id": 2, "name": "B", "price": 19.99}

        r1 = await client.post("/items/", json=item1)
        assert r1.status_code == 200
        r2 = await client.post("/items/", json=item2)
        assert r2.status_code == 200

        d1 = await client.get("/items/dict-list-items")
        assert d1.status_code == 200
        mapping1 = d1.json()
        assert "all" in mapping1
        ids1 = {i["id"] for i in mapping1["all"]}
        assert ids1 == {1, 2}

        d2 = await client.get("/items/dict-list-items")
        assert d2.status_code == 200
        assert d2.json() == mapping1

        t1 = await client.get("/items/tuple-items")
        assert t1.status_code == 200
        tuple1 = t1.json()
        assert isinstance(tuple1, list)  # JSON tuples serialize as lists
        ids_t1 = {i["id"] for i in tuple1}
        assert ids_t1 == {1, 2}

        # Update one item and verify both caches update
        up = await client.patch("/items/update-item/1", json={"name": "A-Edit"})
        assert up.status_code == 200

        d3 = await client.get("/items/dict-list-items")
        assert d3.status_code == 200
        mapping3 = d3.json()
        names3 = {i["name"] for i in mapping3["all"]}
        assert "A-Edit" in names3

        t2 = await client.get("/items/tuple-items")
        assert t2.status_code == 200
        tuple2 = t2.json()
        names_t2 = {i["name"] for i in tuple2}
        assert "A-Edit" in names_t2

        # Delete second item and verify removal
        d_del = await client.delete("/items/delete-item/2")
        assert d_del.status_code == 200

        d4 = await client.get("/items/dict-list-items")
        assert d4.status_code == 200
        mapping4 = d4.json()
        ids4 = {i["id"] for i in mapping4["all"]}
        assert 2 not in ids4

        t3 = await client.get("/items/tuple-items")
        assert t3.status_code == 200
        tuple3 = t3.json()
        ids_t3 = {i["id"] for i in tuple3}
        assert 2 not in ids_t3
