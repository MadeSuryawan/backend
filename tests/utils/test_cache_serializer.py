# tests/utils/test_cache_serializer.py
"""Tests for app/utils/cache_serializer.py module."""

from datetime import datetime
from unittest.mock import patch

import pytest

from app.errors import (
    CacheCompressionError,
    CacheDecompressionError,
    CacheDeserializationError,
    CacheSerializationError,
)
from app.schemas.items import Item
from app.utils.cache_serializer import (
    COMPRESSION_MARKER,
    compress,
    decompress,
    deserialize,
    do_compress,
    serialize,
)


class TestSerialize:
    """Tests for serialize function."""

    def test_serialize_dict(self) -> None:
        """Test serializing a dictionary."""
        data = {"name": "test", "value": 123}
        result = serialize(data)
        assert isinstance(result, str)
        assert "test" in result
        assert "123" in result

    def test_serialize_item_model(self) -> None:
        """Test serializing an Item Pydantic model."""
        item = Item(id=1, name="Test Item", price=9.99)
        result = serialize(item.model_dump())
        assert isinstance(result, str)
        assert "Test Item" in result
        assert "9.99" in result

    def test_serialize_nested_dict(self) -> None:
        """Test serializing nested dictionary."""
        data = {"outer": {"inner": {"deep": "value"}}}
        result = serialize(data)
        assert "deep" in result
        assert "value" in result

    def test_serialize_list_of_dicts(self) -> None:
        """Test serializing list of dictionaries."""
        data = {"items": [{"id": 1}, {"id": 2}]}
        result = serialize(data)
        assert '"items"' in result

    def test_serialize_with_special_types(self) -> None:
        """Test serializing with types that need default=str."""

        data = {"timestamp": datetime.now()}
        result = serialize(data)
        assert isinstance(result, str)

    def test_serialize_error_handling(self) -> None:
        """Test that serialization errors raise CacheSerializationError."""

        class NonSerializable:
            def __repr__(self) -> str:
                mssg = "Cannot repr"
                raise RuntimeError(mssg)

        # Create an object that will fail serialization
        mssg = "Cannot serialize"
        with (
            patch(
                "app.utils.cache_serializer.orjson_dumps",
                side_effect=TypeError(mssg),
            ),
            pytest.raises(CacheSerializationError),
        ):
            serialize({"bad": "data"})


class TestDeserialize:
    """Tests for deserialize function."""

    def test_deserialize_json_string(self) -> None:
        """Test deserializing a JSON string."""
        json_str = '{"name": "test", "value": 123}'
        result = deserialize(json_str)
        assert result == {"name": "test", "value": 123}

    def test_deserialize_list(self) -> None:
        """Test deserializing a JSON array."""
        json_str = "[1, 2, 3]"
        result = deserialize(json_str)
        assert result == [1, 2, 3]

    def test_deserialize_nested_structure(self) -> None:
        """Test deserializing nested JSON."""
        json_str = '{"outer": {"inner": "value"}}'
        result = deserialize(json_str)
        assert result["outer"]["inner"] == "value"

    def test_deserialize_error_handling(self) -> None:
        """Test that deserialization errors raise CacheDeserializationError."""
        with pytest.raises(CacheDeserializationError):
            deserialize("not valid json {{{")


class TestCompress:
    """Tests for compress function."""

    def test_compress_returns_marked_string(self) -> None:
        """Test that compressed data starts with marker."""
        data = "This is test data to compress"
        result = compress(data)
        assert result.startswith(COMPRESSION_MARKER.decode("utf-8"))

    def test_compress_large_data(self) -> None:
        """Test compressing large data."""
        data = "x" * 10000
        result = compress(data)
        # Compressed should be shorter than original + marker
        assert len(result) < len(data)

    def test_compress_error_handling(self) -> None:
        """Test that compression errors raise CacheCompressionError."""
        with (
            patch(
                "app.utils.cache_serializer.gzip_compress",
                side_effect=OSError("Compression failed"),
            ),
            pytest.raises(CacheCompressionError),
        ):
            compress("test data")


class TestDecompress:
    """Tests for decompress function."""

    def test_decompress_returns_original(self) -> None:
        """Test that decompress reverses compress."""
        original = "This is test data"
        compressed = compress(original)
        result = decompress(compressed)
        assert result == original

    def test_decompress_uncompressed_data(self) -> None:
        """Test that uncompressed data is returned as-is."""
        data = "Regular uncompressed string"
        result = decompress(data)
        assert result == data

    def test_decompress_large_data(self) -> None:
        """Test decompressing large data."""
        original = "y" * 10000
        compressed = compress(original)
        result = decompress(compressed)
        assert result == original

    def test_decompress_error_handling(self) -> None:
        """Test that decompression errors raise CacheDecompressionError."""
        # Create invalid compressed data with marker
        invalid_data = COMPRESSION_MARKER.decode("utf-8") + "invalid_base64!!!"
        with (
            patch(
                "app.utils.cache_serializer.gzip_decompress",
                side_effect=OSError("Decompression failed"),
            ),
            pytest.raises(CacheDecompressionError),
        ):
            decompress(invalid_data)


class TestDoCompress:
    """Tests for do_compress function."""

    def test_returns_true_when_exceeds_threshold(self) -> None:
        """Test returns True when data exceeds threshold."""
        data = "x" * 1000
        assert do_compress(data, threshold=500) is True

    def test_returns_false_when_under_threshold(self) -> None:
        """Test returns False when data is under threshold."""
        data = "small"
        assert do_compress(data, threshold=500) is False

    def test_boundary_at_threshold(self) -> None:
        """Test behavior at exact threshold."""
        data = "x" * 100
        assert do_compress(data, threshold=100) is False

    def test_with_unicode_characters(self) -> None:
        """Test with multi-byte unicode characters."""
        # Each emoji is 4 bytes
        data = "🎉" * 25  # 100 bytes
        assert do_compress(data, threshold=50) is True
