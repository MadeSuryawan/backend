# app/middleware/idempotency.py
"""
IdempotencyMiddleware — Starlette BaseHTTPMiddleware for idempotent mutations.

Design decisions (see docs/plan/idempotency.md for full rationale):
- Middleware (not dependency) is the only layer that can short-circuit a route
  handler and return a full cached response body.
- Keys are scoped to the authenticated user (or client IP for unauthenticated
  routes) to prevent cross-user data leakage.
- An atomic Lua script in RedisIdempotencyStore eliminates the TOCTOU race.
- Fail-open: if the store is unavailable, the request proceeds without
  idempotency protection and a warning header is added to the response.
- Short processing TTL (30 s default) prevents permanently stuck keys after
  server crashes.
"""

from base64 import b64decode
from contextlib import suppress
from dataclasses import dataclass, replace
from hashlib import sha256
from re import IGNORECASE
from re import compile as re_compile
from typing import ClassVar

from fastapi import Request
from jose.exceptions import JWTError
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.types import ASGIApp

from app.interfaces.idempotency_store import CompletionRecord, IdempotencyStore
from app.logging import get_logger
from app.managers.token_manager import decode_access_token

logger = get_logger(__name__)

# UUID v4 pattern — 122 bits of entropy, strict format validation.
_UUID_V4_RE = re_compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    IGNORECASE,
)

# Store record status constants
_STATUS_PROCESSING = "processing"
_STATUS_COMPLETED = "completed"
_STATUS_FAILED = "failed"


@dataclass(frozen=True)
class InitContext:
    """Contextual information for idempotency initialization."""

    app: ASGIApp
    store: IdempotencyStore | None
    required_paths: frozenset[tuple[str, str]]
    key_ttl: int = 86400
    processing_ttl: int = 60
    fail_ttl: int = 60


@dataclass(frozen=True)
class IdempotencyContext:
    """Contextual information for idempotency processing."""

    store: IdempotencyStore
    raw_key: str
    redis_key: str
    status_code: int
    req_hash: str
    resp_body: bytes
    path: str
    resp_media_type: str = "application/json"


def _extract_user_scope(request: Request) -> str:
    """
    Derive a user-scoped prefix for the Redis key.

    Tries to decode the Bearer JWT to get the user UUID.
    Falls back to client IP for unauthenticated requests.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        with suppress(JWTError, ValueError):
            token_data = decode_access_token(token)
            if token_data:
                return str(token_data.user_id)
    # Fallback: client IP (for unauthenticated routes like /auth/register)
    client = request.client
    return client.host if client else "anonymous"


def _ensure_bytes(data: bytes | str | memoryview | None) -> bytes:
    """Convert various data types to bytes."""
    if data is None:
        return b""
    if isinstance(data, bytes):
        return data
    if isinstance(data, memoryview):
        return bytes(data)
    return data.encode("utf-8")


async def _capture_response_body(response: Response) -> bytes:
    """Drain the response body into a single bytes object."""
    # Handle streaming responses
    if isinstance(response, StreamingResponse):
        body_parts: list[bytes] = []
        async for chunk in response.body_iterator:
            body_parts.append(_ensure_bytes(chunk))
        return b"".join(body_parts)
    # Handle regular responses with body attribute
    if hasattr(response, "body"):
        return _ensure_bytes(response.body)
    return b""


def _error_response(status_code: int, error: str, detail: str) -> JSONResponse:
    """Create a consistent error response."""
    return JSONResponse(status_code=status_code, content={"error": error, "detail": detail})


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces idempotency for mutation HTTP methods.

    Behaviour summary
    -----------------
    1. Skips non-mutation methods (GET, HEAD, DELETE, OPTIONS) and requests
       without the ``Idempotency-Key`` header.
    2. On required paths (see ``REQUIRED_PATHS``), returns ``400`` if the
       header is absent.
    3. Validates the key is a UUID v4; returns ``400`` on format violation.
    4. Atomically acquires the key in the store:
       - Fresh key → proceeds normally, stores completed response on success.
       - ``processing`` → returns ``409 Conflict``.
       - ``completed`` + same body hash → replays original status + body.
       - ``completed`` + different body hash → returns ``422 Unprocessable Entity``.
    5. On store errors → fail-open (request proceeds, warning header added).
    6. On route exception → ``store.fail()`` with short TTL so client can retry.

    Parameters
    ----------
    app : ASGIApp
        The ASGI application.
    context : InitContext | None
        Configuration context containing store, paths, and TTL settings.
        If None, default values are used.

    Attributes
    ----------
    IDEMPOTENT_METHODS : frozenset[str]
        HTTP methods that support idempotency.
    REQUIRED_PATHS : frozenset[tuple[str, str]]
        Default set of ``(METHOD, path)`` pairs where the header is mandatory.
    """

    IDEMPOTENT_METHODS: ClassVar[frozenset[str]] = frozenset({"POST", "PUT", "PATCH"})

    # Paths where the Idempotency-Key header is MANDATORY.
    # Requests to these paths without the header receive 400 Bad Request.
    REQUIRED_PATHS: ClassVar[frozenset[tuple[str, str]]] = frozenset(
        {
            ("POST", "/blogs/create"),
            ("POST", "/auth/register"),
            ("POST", "/ai/chat"),
            ("POST", "/ai/email-inquiry/"),
            ("POST", "/ai/itinerary-md"),
            ("POST", "/ai/itinerary-txt"),
        },
    )

    def __init__(
        self,
        app: ASGIApp,
        context: InitContext | None = None,
    ) -> None:
        super().__init__(app)
        # Use provided context or create default one
        ctx = context or InitContext(
            app=app,
            store=None,
            required_paths=self.REQUIRED_PATHS,
        )
        # ``store`` may be None at registration time (before lifespan runs).
        # If None, the store is lazily resolved from ``request.app.state``
        # on the first request.  This allows the middleware to be registered
        # in main.py before the lifespan initialises Redis.
        self._store = ctx.store
        self._required_paths = ctx.required_paths
        self._key_ttl = ctx.key_ttl
        self._processing_ttl = ctx.processing_ttl
        self._fail_ttl = ctx.fail_ttl

    def _resolve_store(self, request: Request) -> IdempotencyStore | None:
        """Return the store, lazily resolving from app.state if needed."""
        if self._store is not None:
            return self._store
        return getattr(request.app.state, "idempotency_store", None)

    async def _fail_open(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
        raw_key: str,
        reason: str,
    ) -> Response:
        """Call through to the route handler and mark the response as store-unavailable."""
        logger.warning(reason, idempotency_key=raw_key, path=request.url.path)
        response = await call_next(request)
        response.headers["Idempotency-Store-Unavailable"] = "true"
        return response

    async def _persist_or_release(
        self,
        context: IdempotencyContext,
    ) -> None:
        """Persist the response on success, or release the key on a server error."""
        if context.status_code < 500:
            try:
                await context.store.complete(
                    CompletionRecord(
                        redis_key=context.redis_key,
                        status_code=context.status_code,
                        body=context.resp_body,
                        body_hash=context.req_hash,
                        ttl=self._key_ttl,
                        content_type=context.resp_media_type,
                    ),
                )
            except RedisError:
                logger.warning(
                    "Failed to persist idempotency response — failing open",
                    idempotency_key=context.raw_key,
                )
        else:
            # Server error — release the key so the client can retry.
            with suppress(RedisError):
                await context.store.fail(context.redis_key, self._fail_ttl)

    async def _check_prerequisites(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
        method: str,
        path: str,
        raw_key: str | None,
    ) -> Response | None:
        """
        Validate method, key presence, and key format.

        Returns a ``Response`` to short-circuit ``dispatch``, or ``None`` when
        all prerequisites pass and processing should continue.
        """
        # 1. Skip non-mutation methods entirely.
        if method not in self.IDEMPOTENT_METHODS:
            return await call_next(request)

        # 2. Enforce mandatory header on required paths.
        if raw_key is None:
            if (method, path) in self._required_paths:
                return _error_response(
                    400,
                    "missing_idempotency_key",
                    "Idempotency-Key header is required for this endpoint.",
                )
            # Optional on other mutation paths — skip idempotency.
            return await call_next(request)

        # 3. Validate UUID v4 format. The regex already enforces the 36-char structure.
        if not _UUID_V4_RE.match(raw_key):
            return _error_response(
                400,
                "invalid_idempotency_key",
                "Idempotency-Key must be a valid UUID v4 (xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx).",
            )

        return None

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Process idempotency logic for each incoming request."""
        method = request.method
        path = request.url.path
        raw_key = request.headers.get("Idempotency-Key")

        # Steps 1–3: method guard, key presence, UUID format.
        early_response = await self._check_prerequisites(request, call_next, method, path, raw_key)
        if early_response is not None:
            return early_response

        # At this point, raw_key is validated as a non-None UUID v4.
        assert raw_key is not None

        # 4. Derive user-scoped Redis key and hash the request body.
        scope = _extract_user_scope(request)
        redis_key = f"idemp:{scope}:{raw_key}"
        body = await request.body()
        req_hash = sha256(body).hexdigest()

        # 5. Resolve store — fail-open if not yet initialised.
        store = self._resolve_store(request)
        if store is None:
            return await self._fail_open(
                request,
                call_next,
                raw_key,
                "Idempotency store not initialised — failing open",
            )

        # 6. Attempt atomic acquire — fail-open on store errors.
        try:
            existing = await store.acquire(redis_key, req_hash, self._processing_ttl)
        except RedisError:
            return await self._fail_open(
                request,
                call_next,
                raw_key,
                "Idempotency store unavailable — failing open",
            )

        # 7. Handle existing record or process fresh request.
        if existing:
            return self._handle_existing(existing, req_hash, raw_key)

        context = IdempotencyContext(
            store=store,
            raw_key=raw_key,
            redis_key=redis_key,
            status_code=0,
            req_hash=req_hash,
            resp_body=b"",
            path=path,
        )

        return await self._process_fresh_request(
            request,
            call_next,
            context,
        )

    async def _process_fresh_request(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
        context: IdempotencyContext,
    ) -> Response:
        """Execute the route handler and persist the response."""
        try:
            response = await call_next(request)
        except Exception:
            # On unhandled exception, release the key so the client can retry.
            with suppress(RedisError):
                await context.store.fail(context.redis_key, self._fail_ttl)
            raise

        resp_body = await _capture_response_body(response)
        context = replace(
            context,
            status_code=response.status_code,
            resp_body=resp_body,
            resp_media_type=response.media_type or "application/json",
        )
        await self._persist_or_release(context)

        logger.debug(
            "Idempotency key acquired",
            idempotency_key=context.raw_key,
            idempotency_result="miss",
            path=context.path,
        )

        return Response(
            content=resp_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )

    def _handle_existing(
        self,
        existing: dict,
        req_hash: str,
        raw_key: str,
    ) -> JSONResponse | Response:
        """Route existing record to appropriate handler based on status."""
        status = existing.get("status")
        stored_hash = existing.get("body_hash", "")

        # Conflict detection: same key, different body takes precedence.
        if stored_hash and stored_hash != req_hash:
            return self._handle_conflict(raw_key)

        if status == _STATUS_PROCESSING:
            return self._handle_processing(existing, raw_key)
        if status == _STATUS_COMPLETED:
            return self._replay_response(existing, raw_key)
        return self._handle_failed(existing, raw_key)

    def _handle_conflict(self, raw_key: str) -> JSONResponse:
        """Return 422 when the same key is used with a different request body."""
        logger.warning(
            "Idempotency key reused with different body",
            idempotency_key=raw_key,
            idempotency_result="conflict",
        )
        return _error_response(
            422,
            "idempotency_conflict",
            "Idempotency-Key was previously used with a different request body.",
        )

    def _handle_processing(self, _existing: dict, raw_key: str) -> JSONResponse:
        """Return 409 when a request with the same key is already being processed."""
        logger.warning(
            "Duplicate request while processing",
            idempotency_key=raw_key,
            idempotency_result="hit_processing",
        )
        return _error_response(
            409,
            "request_in_progress",
            "A request with this Idempotency-Key is already being processed.",
        )

    def _replay_response(self, existing: dict, raw_key: str) -> Response:
        """Replay a completed response from the store."""
        status_code = existing.get("status_code", 200)
        encoded_body = existing.get("body", "")
        resp_body = b64decode(encoded_body) if encoded_body else b""
        media_type = existing.get("content_type", "application/json")

        logger.debug(
            "Replaying idempotent response",
            idempotency_key=raw_key,
            idempotency_result="hit_completed",
            idempotency_replay_status=status_code,
        )
        return Response(
            content=resp_body,
            status_code=status_code,
            media_type=media_type,
            headers={"Idempotent-Replayed": "true"},
        )

    def _handle_failed(self, _existing: dict, raw_key: str) -> JSONResponse:
        """Return 409 when the previous request failed, allowing the client to retry."""
        logger.debug(
            "Idempotency key in failed state — allowing retry",
            idempotency_key=raw_key,
            idempotency_result="failed",
        )
        return JSONResponse(
            status_code=409,
            content={
                "error": "request_failed",
                "detail": "Previous request with this key failed. Please retry after a moment.",
            },
            headers={"Retry-After": str(self._fail_ttl)},
        )
