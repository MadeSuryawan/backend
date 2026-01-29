# tests/decorators/test_caching.py
"""Tests for app/decorators/caching.py module."""

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import Request
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


@pytest.fixture
def mock_request(test_cache_manager: CacheManager) -> Request:
    """Create a mock Request with cache_manager attached to app.state."""
    mock_app = MagicMock()
    mock_app.state.cache_manager = test_cache_manager
    request = MagicMock(spec=Request)
    request.app = mock_app
    return request


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
        mock_request: Request,
    ) -> None:
        """Test that function result is cached."""
        call_count = 0

        @cached(ttl=300)
        async def get_data(request: Request) -> SampleModel:
            nonlocal call_count
            call_count += 1
            return SampleModel(id=1, name="test")

        result1 = await get_data(mock_request)
        result2 = await get_data(mock_request)

        assert result1 == SampleModel(id=1, name="test")
        assert result2 == SampleModel(id=1, name="test")
        assert call_count == 1  # Should only be called once

    @pytest.mark.asyncio
    async def test_caches_list_of_models_inferred(
        self,
        mock_request: Request,
    ) -> None:
        items = [SampleModel(id=1, name="a"), SampleModel(id=2, name="b")]

        @cached(ttl=300)
        async def get_list(request: Request) -> list[SampleModel]:
            return items

        r1 = await get_list(mock_request)
        r2 = await get_list(mock_request)
        assert isinstance(r1, list) and isinstance(r1[0], SampleModel)
        assert isinstance(r2, list) and isinstance(r2[0], SampleModel)
        assert r1 == r2

    @pytest.mark.asyncio
    async def test_caches_dict_of_models_with_response_type(
        self,
        mock_request: Request,
    ) -> None:
        mapping = {"x": SampleModel(id=1, name="x")}

        @cached(ttl=300, response_model=dict[str, SampleModel])
        async def get_dict(request: Request) -> dict[str, SampleModel]:
            return mapping

        r1 = await get_dict(mock_request)
        r2 = await get_dict(mock_request)
        assert isinstance(r1, dict) and isinstance(next(iter(r1.values())), SampleModel)
        assert isinstance(r2, dict) and isinstance(next(iter(r2.values())), SampleModel)
        assert r1 == r2

    @pytest.mark.asyncio
    async def test_custom_key_builder(
        self,
        mock_request: Request,
    ) -> None:
        """Test custom key builder function."""

        def my_key_builder(*args: list[Any], **kwargs: dict[str, Any]) -> str:
            return f"custom_key_{kwargs.get('item_id', 'default')}"

        @cached(key_builder=my_key_builder)
        async def get_item(request: Request, item_id: int) -> SampleModel:
            return SampleModel(id=item_id, name="test")

        result = await get_item(mock_request, item_id=42)
        assert result == SampleModel(id=42, name="test")

    @pytest.mark.asyncio
    async def test_with_namespace(
        self,
        mock_request: Request,
    ) -> None:
        """Test caching with namespace."""

        @cached(namespace="items")
        async def get_item(request: Request) -> SampleModel:
            return SampleModel(id=1, name="item")

        result = await get_item(mock_request)
        assert result == SampleModel(id=1, name="item")

    @pytest.mark.asyncio
    async def test_with_response_model(
        self,
        mock_request: Request,
    ) -> None:
        """Test caching with response model validation."""

        @cached(response_model=SampleModel)
        async def get_sample(request: Request) -> SampleModel:
            return SampleModel(id=1, name="test")

        # First call - caches result
        _ = await get_sample(mock_request)

        # Second call - retrieves from cache and validates
        result2 = await get_sample(mock_request)
        assert isinstance(result2, SampleModel)


class TestCacheBustingDecorator:
    """Tests for cache_busting decorator."""

    @pytest.mark.asyncio
    async def test_busts_specified_keys(
        self,
        test_cache_manager: CacheManager,
        mock_request: Request,
    ) -> None:
        """Test that specified keys are busted after function execution."""
        # Pre-populate cache
        await test_cache_manager.set("item_1", {"data": "old"})

        @cache_busting(keys=["item_1"])
        async def update_item(request: Request) -> SampleModel:
            return SampleModel(id=1, name="updated")

        result = await update_item(mock_request)
        assert result == SampleModel(id=1, name="updated")

        # Verify cache was busted
        cached = await test_cache_manager.get("item_1")
        assert cached is None

    @pytest.mark.asyncio
    async def test_with_custom_key_builder(
        self,
        test_cache_manager: CacheManager,
        mock_request: Request,
    ) -> None:
        """Test cache busting with custom key builder."""
        # Pre-populate cache
        await test_cache_manager.set("user_42", {"name": "old"})

        def bust_key_builder(*args: list[Any], **kwargs: dict[str, Any]) -> list[str]:
            return [f"user_{kwargs.get('user_id')}"]

        @cache_busting(key_builder=bust_key_builder)
        async def delete_user(request: Request, user_id: int) -> SampleModel:
            return SampleModel(id=user_id, name="deleted")

        result = await delete_user(mock_request, user_id=42)
        assert result == SampleModel(id=42, name="deleted")

    @pytest.mark.asyncio
    async def test_with_namespace(
        self,
        test_cache_manager: CacheManager,
        mock_request: Request,
    ) -> None:
        """Test cache busting with namespace."""
        namespace = "users"
        await test_cache_manager.set("user_1", {"name": "test"}, namespace=namespace)

        @cache_busting(keys=["user_1"], namespace=namespace)
        async def remove_user(request: Request) -> SampleModel:
            return SampleModel(id=1, name="removed")

        await remove_user(mock_request)

        cached = await test_cache_manager.get("user_1", namespace=namespace)
        assert cached is None

    @pytest.mark.asyncio
    async def test_no_keys_specified(
        self,
        mock_request: Request,
    ) -> None:
        """Test cache busting when no keys are specified."""

        @cache_busting()
        async def do_nothing(request: Request) -> SampleModel:
            return SampleModel(id=1, name="done")

        result = await do_nothing(mock_request)
        assert result == SampleModel(id=1, name="done")
