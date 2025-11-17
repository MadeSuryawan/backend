"""Type definitions for caching module."""

from collections.abc import Callable, Coroutine
from typing import Any

CacheValue = Any
CacheKey = str
CacheCallback = Callable[..., Coroutine[Any, Any, CacheValue]]
CacheSerializer = Callable[[Any], str]
CacheDeserializer = Callable[[str], Any]
