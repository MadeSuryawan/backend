# app/interfaces/__init__.py
"""Interfaces (Protocols) for dependency inversion across the application."""

from app.interfaces.idempotency_store import CompletionRecord, IdempotencyStore

__all__ = ["CompletionRecord", "IdempotencyStore"]
