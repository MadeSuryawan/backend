# tests/decorators/test_caching.py
"""Tests for app/decorators/caching.py module."""

from collections.abc import AsyncGenerator
from typing import Any

import pytest
from pydantic import BaseModel

from app.decorators.caching import (
    _generate_cache_key,
    cache_busting,
    cached,
    validate_cache,
)
from app.managers.cache_manager import CacheManager


class SampleModel(BaseModel):
    """Sample Pydantic model for testing."""

    id: int
    name: str


@pytest.fixture
async def test_cache_manager() -> AsyncGenerator[CacheManager]:
    """Create a test cache manager with memory client."""
    manager = CacheManager()
    await manager.initialize()
    await manager.clear()
    yield manager
    await manager.shutdown()


class TestGenerateCacheKey:
    """Tests for _generate_cache_key function."""

    def test_generates_key_from_function_name(self) -> None:
        """Test key generation with just function name."""
        key = _generate_cache_key("my_function")
        assert isinstance(key, str)
        assert len(key) == 16

    def test_generates_different_keys_for_different_args(self) -> None:
        """Test that different args produce different keys."""
        key1 = _generate_cache_key("func", [1])
        key2 = _generate_cache_key("func", [3])
        assert key1 != key2

    def test_generates_different_keys_for_different_kwargs(self) -> None:
        """Test that different kwargs produce different keys."""
        key1 = _generate_cache_key("func", name={"a": "alice"})
        key2 = _generate_cache_key("func", name={"b": "bob"})
        assert key1 != key2

    def test_handles_complex_args(self) -> None:
        """Test with complex argument types."""
        key = _generate_cache_key("func", [1, 2, 3], name={"nested": "dict"})
        assert isinstance(key, str)

    def test_handles_non_serializable_args(self) -> None:
        """Test handling of non-serializable arguments."""

        class NonSerializable:
            pass

        # Should not raise, just skip the argument
        key = _generate_cache_key("func", [NonSerializable()])
        assert isinstance(key, str)

    def test_consistent_keys_for_same_input(self) -> None:
        """Test that same inputs produce same key."""
        key1 = _generate_cache_key("func", [1], name={"test": "value"})
        key2 = _generate_cache_key("func", [1], name={"test": "value"})
        assert key1 == key2


class TestValidateResponse:
    """Tests for validate_response function."""

    def test_validate_dict_response(self) -> None:
        """Test validating dict against dict type."""
        data = {"id": 1, "name": "test"}
        result = validate_cache(data, SampleModel)
        assert isinstance(result, SampleModel)
        assert result.id == 1

    def test_validate_pydantic_model(self) -> None:
        """Test validating dict against Pydantic model."""
        data = {"id": 1, "name": "test"}
        result = validate_cache(data, SampleModel)
        assert isinstance(result, SampleModel)
        assert result.id == 1

    def test_validate_list_of_models(self) -> None:
        """Test validating list of dicts against list of models."""
        data = {"id": 1, "name": "a"}
        data2 = {"id": 2, "name": "b"}
        result = validate_cache(data, SampleModel)
        result2 = validate_cache(data2, SampleModel)
        assert isinstance(result, SampleModel)
        assert isinstance(result2, SampleModel)


class TestCachedDecorator:
    """Tests for cached decorator."""

    @pytest.mark.asyncio
    async def test_caches_function_result(
        self,
        test_cache_manager: CacheManager,
    ) -> None:
        """Test that function result is cached."""
        call_count = 0

        @cached(test_cache_manager, ttl=300)
        async def get_data() -> SampleModel:
            nonlocal call_count
            call_count += 1
            return SampleModel(id=1, name="test")

        result1 = await get_data()
        result2 = await get_data()

        assert result1 == SampleModel(id=1, name="test")  # .model_dump()
        assert result2 == SampleModel(id=1, name="test")  # .model_dump()
        assert call_count == 1  # Should only be called once

    @pytest.mark.asyncio
    async def test_caches_list_of_models_inferred(
        self,
        test_cache_manager: CacheManager,
    ) -> None:
        items = [SampleModel(id=1, name="a"), SampleModel(id=2, name="b")]

        @cached(test_cache_manager, ttl=300)
        async def get_list() -> list[SampleModel]:
            return items

        r1 = await get_list()
        r2 = await get_list()
        assert isinstance(r1, list) and isinstance(r1[0], SampleModel)
        assert isinstance(r2, list) and isinstance(r2[0], SampleModel)
        assert r1 == r2

    @pytest.mark.asyncio
    async def test_caches_dict_of_models_with_response_type(
        self,
        test_cache_manager: CacheManager,
    ) -> None:
        mapping = {"x": SampleModel(id=1, name="x")}

        @cached(test_cache_manager, ttl=300, response_model=dict[str, SampleModel])
        async def get_dict() -> dict[str, SampleModel]:
            return mapping

        r1 = await get_dict()
        r2 = await get_dict()
        assert isinstance(r1, dict) and isinstance(next(iter(r1.values())), SampleModel)
        assert isinstance(r2, dict) and isinstance(next(iter(r2.values())), SampleModel)
        assert r1 == r2

    @pytest.mark.asyncio
    async def test_custom_key_builder(
        self,
        test_cache_manager: CacheManager,
    ) -> None:
        """Test custom key builder function."""

        def my_key_builder(*args: list[Any], **kwargs: dict[str, Any]) -> str:
            return f"custom_key_{kwargs.get('item_id', 'default')}"

        @cached(test_cache_manager, key_builder=my_key_builder)
        async def get_item(item_id: int) -> SampleModel:
            return SampleModel(id=item_id, name="test")

        result = await get_item(item_id=42)
        assert result == SampleModel(id=42, name="test")

    @pytest.mark.asyncio
    async def test_with_namespace(
        self,
        test_cache_manager: CacheManager,
    ) -> None:
        """Test caching with namespace."""

        @cached(test_cache_manager, namespace="items")
        async def get_item() -> SampleModel:
            return SampleModel(id=1, name="item")

        result = await get_item()
        assert result == SampleModel(id=1, name="item")

    @pytest.mark.asyncio
    async def test_with_response_model(
        self,
        test_cache_manager: CacheManager,
    ) -> None:
        """Test caching with response model validation."""

        @cached(test_cache_manager, response_model=SampleModel)
        async def get_sample() -> SampleModel:
            return SampleModel(id=1, name="test")

        # First call - caches result
        _ = await get_sample()

        # Second call - retrieves from cache and validates
        result2 = await get_sample()
        assert isinstance(result2, SampleModel)


class TestCacheBustingDecorator:
    """Tests for cache_busting decorator."""

    @pytest.mark.asyncio
    async def test_busts_specified_keys(
        self,
        test_cache_manager: CacheManager,
    ) -> None:
        """Test that specified keys are busted after function execution."""
        # Pre-populate cache
        await test_cache_manager.set("item_1", {"data": "old"})

        @cache_busting(test_cache_manager, keys=["item_1"])
        async def update_item() -> SampleModel:
            return SampleModel(id=1, name="updated")

        result = await update_item()
        assert result == SampleModel(id=1, name="updated")

        # Verify cache was busted
        cached = await test_cache_manager.get("item_1")
        assert cached is None

    @pytest.mark.asyncio
    async def test_with_custom_key_builder(
        self,
        test_cache_manager: CacheManager,
    ) -> None:
        """Test cache busting with custom key builder."""
        # Pre-populate cache
        await test_cache_manager.set("user_42", {"name": "old"})

        def bust_key_builder(*args: list[Any], **kwargs: dict[str, Any]) -> list[str]:
            return [f"user_{kwargs.get('user_id')}"]

        @cache_busting(test_cache_manager, key_builder=bust_key_builder)
        async def delete_user(user_id: int) -> SampleModel:
            return SampleModel(id=user_id, name="deleted")

        result = await delete_user(user_id=42)
        assert result == SampleModel(id=42, name="deleted")

    @pytest.mark.asyncio
    async def test_with_namespace(
        self,
        test_cache_manager: CacheManager,
    ) -> None:
        """Test cache busting with namespace."""
        namespace = "users"
        await test_cache_manager.set("user_1", {"name": "test"}, namespace=namespace)

        @cache_busting(test_cache_manager, keys=["user_1"], namespace=namespace)
        async def remove_user() -> SampleModel:
            return SampleModel(id=1, name="removed")

        await remove_user()

        cached = await test_cache_manager.get("user_1", namespace=namespace)
        assert cached is None

    @pytest.mark.asyncio
    async def test_no_keys_specified(
        self,
        test_cache_manager: CacheManager,
    ) -> None:
        """Test cache busting when no keys are specified."""

        @cache_busting(test_cache_manager)
        async def do_nothing() -> SampleModel:
            return SampleModel(id=1, name="done")

        result = await do_nothing()
        assert result == SampleModel(id=1, name="done")
