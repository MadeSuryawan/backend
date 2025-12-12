"""
Serialization and compression utilities for caching.

Uses orjson for high-performance JSON serialization/deserialization.
Falls back to standard json if orjson is not available.
"""

from base64 import b64decode, b64encode
from gzip import compress as gzip_compress
from gzip import decompress as gzip_decompress
from logging import getLogger
from typing import Any

from pydantic_core import PydanticSerializationError

from app.configs import file_logger
from app.errors import (
    CacheCompressionError,
    CacheDecompressionError,
    CacheDeserializationError,
    CacheSerializationError,
)

# from app.schemas.items import Item

# Try to use orjson for better performance, fallback to standard json
try:
    from orjson import OPT_NON_STR_KEYS, OPT_SERIALIZE_NUMPY
    from orjson import dumps as orjson_dumps
    from orjson import loads as orjson_loads

    _HAS_ORJSON = True
except ImportError:
    from json import dumps as json_dumps
    from json import loads as json_loads

    _HAS_ORJSON = False

logger = file_logger(getLogger(__name__))

COMPRESSION_MARKER = b"\x00GZIP\x00"


def serialize(value: object) -> str:
    """
    Serialize value to JSON string.

    Uses orjson for better performance when available.

    Args:
        value: Value to serialize.

    Returns:
        JSON serialized string.

    Raises:
        CacheSerializationError: If serialization fails.
    """
    try:
        # if isinstance(value, Item):
        #     return value.model_dump_json()

        if _HAS_ORJSON:
            # orjson returns bytes, decode to string
            # OPT_SERIALIZE_NUMPY handles numpy types if present
            return orjson_dumps(
                value,
                default=str,
                option=OPT_SERIALIZE_NUMPY | OPT_NON_STR_KEYS,
            ).decode("utf-8")
        return json_dumps(value, default=str, sort_keys=False)
    except (PydanticSerializationError, TypeError, ValueError) as e:
        logger.exception("Serialization failed")
        raise CacheSerializationError from e


def deserialize(value: str) -> dict[str, Any]:
    """
    Deserialize JSON string to value.

    Uses orjson for better performance when available.

    Args:
        value: JSON string to deserialize.

    Returns:
        Deserialized value.

    Raises:
        CacheDeserializationError: If deserialization fails.
    """
    try:
        if _HAS_ORJSON:
            return orjson_loads(value)
        return json_loads(value)
    except Exception as e:
        # Handle both JSONDecodeError and JSONDecodeError
        if isinstance(e, (ValueError, TypeError)):
            logger.exception("Deserialization failed")
            raise CacheDeserializationError from e
        raise


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
        raise CacheCompressionError from e


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
        raise CacheDecompressionError from e


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
