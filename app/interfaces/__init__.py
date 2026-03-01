# app/interfaces/__init__.py
"""Interfaces (Protocols) for dependency inversion across the application."""

from app.interfaces.cache_client import CacheClientProtocol, is_debug_enabled
from app.interfaces.idempotency_store import CompletionRecord, IdempotencyStore

__all__ = [
    "CacheClientProtocol",
    "CompletionRecord",
    "IdempotencyStore",
    "is_debug_enabled",
]
