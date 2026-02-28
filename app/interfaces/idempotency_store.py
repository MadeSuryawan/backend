# app/interfaces/idempotency_store.py
"""
IdempotencyStore Protocol — Dependency Inversion for idempotency persistence.

Defines the minimal interface that any idempotency store backend must satisfy.
The middleware depends on this protocol, not on any concrete implementation,
satisfying the Dependency Inversion Principle (SOLID-D).
"""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class CompletionRecord:
    """
    Value object that bundles all data needed to persist a completed response.

    Passed as a single argument to ``IdempotencyStore.complete()`` to keep the
    method within the project's five-parameter limit (ruff PLR0913).

    Attributes
    ----------
    redis_key : str
        Fully-qualified store key (e.g. ``idemp:{user}:{uuid}``).
    status_code : int
        Original HTTP status code to replay verbatim.
    body : bytes
        Raw response body bytes to replay verbatim.
    body_hash : str
        SHA-256 hex digest of the original request body.
    ttl : int
        Seconds until the completed record expires (e.g. 86 400 for 24 h).
    content_type : str
        ``Content-Type`` of the original response (e.g. ``application/json``).
        Stored so that replays advertise the correct media type.
    """

    redis_key: str
    status_code: int
    body: bytes
    body_hash: str
    ttl: int
    content_type: str = field(default="application/json")


@runtime_checkable
class IdempotencyStore(Protocol):
    """
    Protocol for idempotency key persistence.

    Any concrete implementation (Redis, PostgreSQL, in-memory) must satisfy
    this interface. The middleware is programmed against this protocol only.

    Key lifecycle
    -------------
    absent → processing (acquire) → completed (complete)
                                  ↘ failed/absent (fail)

    Notes
    -----
    All methods are async. Implementations must be safe for concurrent use
    across multiple application instances sharing the same backing store.
    """

    async def acquire(
        self,
        redis_key: str,
        body_hash: str,
        processing_ttl: int,
    ) -> dict | None:
        """
        Atomically attempt to claim an idempotency key.

        Parameters
        ----------
        redis_key : str
            The fully-qualified store key (e.g. ``idemp:{user}:{uuid}``).
        body_hash : str
            SHA-256 hex digest of the request body. Stored for conflict detection.
        processing_ttl : int
            Seconds until the ``processing`` record expires automatically.
            Prevents permanently stuck keys after server crashes.

        Returns
        -------
        dict | None
            ``None`` if the key was newly acquired — the caller should proceed
            with normal request processing.

            A ``dict`` with at minimum ``{"status": str, "body_hash": str}``
            (and optionally ``"status_code": int``, ``"body": str``) if the
            key already existed. The middleware interprets the dict to decide
            whether to replay, reject with 409, or reject with 422.
        """
        ...

    async def complete(self, record: CompletionRecord) -> None:
        """
        Persist the completed response for future replay.

        Parameters
        ----------
        record : CompletionRecord
            Value object containing all fields needed to store the response.
        """
        ...

    async def fail(self, redis_key: str, ttl: int) -> None:
        """
        Release or expire a key that failed so a retry is allowed.

        Parameters
        ----------
        redis_key : str
            The fully-qualified store key.
        ttl : int
            Short TTL in seconds (e.g. 60) before the key expires and the
            client may retry with the same idempotency key.
        """
        ...
