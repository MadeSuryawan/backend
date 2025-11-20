"""Serialization and compression utilities for caching."""

from base64 import b64decode, b64encode
from gzip import compress as gzip_compress
from gzip import decompress as gzip_decompress
from json import JSONDecodeError, dumps, loads
from logging import Logger, getLogger
from typing import Any

from pydantic_core import PydanticSerializationError, ValidationError
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from app.errors.exceptions import (
    CacheCompressionError,
    CacheDecompressionError,
    CacheDeserializationError,
    CacheSerializationError,
)
from app.schemas.items import Item

logger: Logger = getLogger(__name__)

COMPRESSION_MARKER = b"\x00GZIP\x00"


def serialize(value: Item | dict[str, Any]) -> str:
    """
    Serialize value to JSON string.

    Args:
        value: Value to serialize.

    Returns:
        JSON serialized string.

    Raises:
        CacheSerializationError: If serialization fails.
    """
    try:
        if isinstance(value, Item):
            return value.model_dump_json()
        return dumps(value, default=str, sort_keys=False)
    except (PydanticSerializationError, JSONDecodeError) as e:
        logger.exception("Serialization failed")
        mssg = f"Cannot serialize value: {e}"
        raise CacheSerializationError(mssg) from e


def deserialize(value: str) -> Item | dict:
    """
    Deserialize JSON string to value.

    Args:
        value: JSON string to deserialize.

    Returns:
        Deserialized value.

    Raises:
        CacheDeserializationError: If deserialization fails.
    """
    try:
        if "items" in (items_dict := loads(value)):  # and Item.model_validate(items_dict["items"])
            logger.debug(f"{items_dict["items"]=}")
            item_list: list[Item] = [Item.model_validate_json(item) for item in items_dict["items"]]
            return {"items": item_list}

        return Item.model_validate_json(value)
    except ValidationError as e:
        logger.exception("Deserialization failed")
        mssg = f"Cannot deserialize value: {e}"
        raise CacheDeserializationError(mssg) from e


def compress(data: str) -> str:
    """
    Compress data using gzip.

    Args:
        data: Data to compress.

    Returns:
        Compressed data as base64-encoded string with marker.

    Raises:
        CacheCompressionError: If compression fails.
    """
    try:
        compressed = gzip_compress(data.encode("utf-8"))
        return COMPRESSION_MARKER.decode("utf-8") + b64encode(compressed).decode("utf-8")
    except Exception as e:
        logger.exception("Compression failed")
        mssg = f"Cannot compress data: {e}"
        raise CacheCompressionError(mssg) from e


def decompress(data: str) -> str:
    """
    Decompress gzip data.

    Args:
        data: Compressed base64-encoded data with marker.

    Returns:
        Decompressed string.

    Raises:
        CacheDecompressionError: If decompression fails.
    """
    try:
        if not data.startswith(COMPRESSION_MARKER.decode("utf-8")):
            return data

        encoded = data[len(COMPRESSION_MARKER.decode("utf-8")) :]
        compressed = b64decode(encoded.encode("utf-8"))
        return gzip_decompress(compressed).decode("utf-8")
    except Exception as e:
        logger.exception("Decompression failed")
        mssg = f"Cannot decompress data: {e}"
        raise CacheDecompressionError(mssg) from e


def do_compress(data: str, threshold: int) -> bool:
    """
    Determine if data should be compressed.

    Args:
        data: Data to check.
        threshold: Size threshold in bytes.

    Returns:
        True if data size exceeds threshold.
    """
    return len(data.encode("utf-8")) > threshold
