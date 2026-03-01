# app/interfaces/__init__.py
"""Interfaces (Protocols) for dependency inversion across the application."""

from app.interfaces.cache_client import CacheClientProtocol, is_debug_enabled
from app.interfaces.idempotency_store import CompletionRecord, IdempotencyStore
from app.interfaces.media_storage import StorageService

__all__ = [
    "CacheClientProtocol",
    "CompletionRecord",
    "IdempotencyStore",
    "StorageService",
    "is_debug_enabled",
]
