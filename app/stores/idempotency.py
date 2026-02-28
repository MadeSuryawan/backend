# app/stores/idempotency.py
"""
RedisIdempotencyStore — Redis-backed implementation of IdempotencyStore.

Uses an atomic Lua script for the ``acquire`` operation to eliminate the
TOCTOU race condition present in a naive GET → SET two-step approach.

Key schema
----------
Redis key : ``idemp:{scope}:{idempotency_key}``
Value     : JSON-encoded record with fields:
    - status       : "processing" | "completed" | "failed"
    - body_hash    : SHA-256 hex digest of the original request body
    - status_code  : int  (only when status == "completed")
    - body         : base64-encoded response bytes (only when status == "completed")
    - content_type : str  (only when status == "completed"; e.g. "application/json")
"""

import base64
import json

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.interfaces.idempotency_store import CompletionRecord
from app.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Lua script — atomic check-and-set
# ---------------------------------------------------------------------------
# If the key already exists, return its current value (no modification).
# If the key does not exist, set it to ARGV[1] with TTL ARGV[2] and return nil.
# This eliminates the TOCTOU gap of a separate GET + SET NX.
_ACQUIRE_SCRIPT = """
local existing = redis.call('GET', KEYS[1])
if existing then
    return existing
end
redis.call('SET', KEYS[1], ARGV[1], 'EX', tonumber(ARGV[2]))
return nil
"""


class RedisIdempotencyStore:
    """
    Redis-backed idempotency store.

    Parameters
    ----------
    redis : Redis
        An already-connected ``redis.asyncio.Redis`` instance.
        Obtained from ``CacheManager.redis_client.client``.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._acquire_script = self._redis.register_script(_ACQUIRE_SCRIPT)

    async def acquire(
        self,
        redis_key: str,
        body_hash: str,
        processing_ttl: int,
    ) -> dict | None:
        """
        Atomically claim a key or return the existing record.

        Returns ``None`` on a fresh claim (caller should proceed).
        Returns the existing record dict if the key was already set.
        """
        processing_record = json.dumps({"status": "processing", "body_hash": body_hash})
        try:
            result = await self._acquire_script(
                keys=[redis_key],
                args=[processing_record, str(processing_ttl)],
            )
        except RedisError:
            logger.exception("RedisIdempotencyStore.acquire failed for key %s", redis_key)
            raise

        if result is None:
            return None  # Key was freshly acquired — caller proceeds normally

        raw = result.decode("utf-8") if isinstance(result, bytes) else result
        return json.loads(raw)

    async def complete(self, record: CompletionRecord) -> None:
        """Overwrite the processing record with the completed response."""
        payload = json.dumps(
            {
                "status": "completed",
                "status_code": record.status_code,
                "body": base64.b64encode(record.body).decode("ascii"),
                "body_hash": record.body_hash,
                "content_type": record.content_type,
            },
        )
        try:
            await self._redis.set(record.redis_key, payload, ex=record.ttl)
        except RedisError:
            logger.exception("RedisIdempotencyStore.complete failed for key %s", record.redis_key)
            raise

    async def fail(self, redis_key: str, ttl: int) -> None:
        """
        Mark a key as failed with a short TTL.

        After ``ttl`` seconds the key expires and the client may retry
        with the same idempotency key.
        """
        record = json.dumps({"status": "failed"})
        try:
            await self._redis.set(redis_key, record, ex=ttl)
        except RedisError:
            logger.exception("RedisIdempotencyStore.fail failed for key %s", redis_key)
            raise
