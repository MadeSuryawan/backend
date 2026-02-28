# tests/middleware/test_idempotency_middleware.py
"""
Unit tests for IdempotencyMiddleware.

Uses a lightweight ASGI test app with a mock IdempotencyStore so that
no Redis connection is required.  Each test exercises a distinct branch
of the middleware's dispatch logic.
"""

import base64
import hashlib
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from redis.exceptions import RedisError

from app.middleware.idempotency import IdempotencyMiddleware, InitContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_UUID = "550e8400-e29b-41d4-a716-446655440000"
INVALID_UUID = "not-a-uuid"
REQUIRED_PATH = "/blogs/create"
OPTIONAL_PATH = "/some/other/post"

_REQUIRED_PATHS: frozenset[tuple[str, str]] = frozenset({("POST", REQUIRED_PATH)})

type AcquireReturn = dict[str, str | int] | dict[str, str] | None


def _make_store(
    acquire_return: AcquireReturn = None,
    acquire_side_effect: Exception | None = None,
    complete_side_effect: Exception | None = None,
    fail_side_effect: Exception | None = None,
) -> MagicMock:
    """Build a mock IdempotencyStore."""
    store = MagicMock()
    store.acquire = AsyncMock(return_value=acquire_return, side_effect=acquire_side_effect)
    store.complete = AsyncMock(side_effect=complete_side_effect)
    store.fail = AsyncMock(side_effect=fail_side_effect)
    return store


def _make_app(store: MagicMock | None = None) -> FastAPI:
    """Build a minimal FastAPI app with IdempotencyMiddleware injected."""
    app = FastAPI()
    context = InitContext(
        app=app,
        store=store,
        required_paths=_REQUIRED_PATHS,
    )
    app.add_middleware(IdempotencyMiddleware, context=context)

    @app.post(REQUIRED_PATH)
    async def create_blog() -> JSONResponse:
        return JSONResponse({"created": True}, status_code=201)

    @app.post(OPTIONAL_PATH)
    async def optional_post() -> JSONResponse:
        return JSONResponse({"ok": True})

    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_store() -> MagicMock:
    """Store that always returns None (fresh key)."""
    return _make_store(acquire_return=None)


@pytest.fixture
def app_with_fresh_store(fresh_store: MagicMock) -> FastAPI:
    return _make_app(fresh_store)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_first_request_proceeds_and_stores_response(
    app_with_fresh_store: FastAPI,
    fresh_store: MagicMock,
) -> None:
    """A fresh idempotency key should pass through and store the response."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_fresh_store),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            REQUIRED_PATH,
            json={"title": "Hello"},
            headers={"Idempotency-Key": VALID_UUID},
        )

    assert resp.status_code == 201
    fresh_store.acquire.assert_awaited_once()
    fresh_store.complete.assert_awaited_once()


async def test_replay_completed_response() -> None:
    """A completed key with matching body hash should replay the stored response."""
    body_bytes = b'{"title": "Hello"}'
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    stored_body = base64.b64encode(b'{"created":true}').decode()
    existing = {
        "status": "completed",
        "status_code": 201,
        "body": stored_body,
        "body_hash": body_hash,
        "content_type": "application/json",
    }
    store = _make_store(acquire_return=existing)
    app = _make_app(store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            REQUIRED_PATH,
            content=body_bytes,
            headers={"Idempotency-Key": VALID_UUID, "Content-Type": "application/json"},
        )

    assert resp.status_code == 201
    assert resp.headers.get("Idempotent-Replayed") == "true"
    assert "application/json" in resp.headers.get("content-type", "")
    store.complete.assert_not_awaited()


async def test_concurrent_duplicate_returns_409() -> None:
    """A key in 'processing' state should return 409 Conflict."""

    body_bytes = b'{"title": "Hello"}'
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    existing = {"status": "processing", "body_hash": body_hash}
    store = _make_store(acquire_return=existing)
    app = _make_app(store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            REQUIRED_PATH,
            content=body_bytes,
            headers={"Idempotency-Key": VALID_UUID, "Content-Type": "application/json"},
        )

    assert resp.status_code == 409
    assert resp.json()["error"] == "request_in_progress"


async def test_body_mismatch_returns_422() -> None:
    """Same key but different body hash should return 422 Unprocessable Entity."""
    existing = {
        "status": "completed",
        "status_code": 201,
        "body": base64.b64encode(b'{"created":true}').decode(),
        "body_hash": "aaaaaa",  # different from actual request body hash
    }
    store = _make_store(acquire_return=existing)
    app = _make_app(store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            REQUIRED_PATH,
            json={"title": "Different body"},
            headers={"Idempotency-Key": VALID_UUID},
        )

    assert resp.status_code == 422
    assert resp.json()["error"] == "idempotency_conflict"


async def test_missing_key_on_required_path_returns_400(fresh_store: MagicMock) -> None:
    """Missing Idempotency-Key on a required path should return 400."""
    app = _make_app(fresh_store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(REQUIRED_PATH, json={"title": "Hello"})

    assert resp.status_code == 400
    assert resp.json()["error"] == "missing_idempotency_key"
    fresh_store.acquire.assert_not_awaited()


async def test_missing_key_on_optional_path_passes_through(fresh_store: MagicMock) -> None:
    """Missing Idempotency-Key on a non-required path should pass through normally."""
    app = _make_app(fresh_store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(OPTIONAL_PATH, json={})

    assert resp.status_code == 200
    fresh_store.acquire.assert_not_awaited()


async def test_invalid_uuid_format_returns_400(fresh_store: MagicMock) -> None:
    """A non-UUID v4 Idempotency-Key should return 400."""
    app = _make_app(fresh_store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            REQUIRED_PATH,
            json={"title": "Hello"},
            headers={"Idempotency-Key": INVALID_UUID},
        )

    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_idempotency_key"
    fresh_store.acquire.assert_not_awaited()


async def test_store_unavailable_fails_open() -> None:
    """If the store raises an exception, the request should proceed (fail-open)."""
    store = _make_store(acquire_side_effect=RedisError("Redis down"))
    app = _make_app(store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            REQUIRED_PATH,
            json={"title": "Hello"},
            headers={"Idempotency-Key": VALID_UUID},
        )

    # Request should succeed despite store failure
    assert resp.status_code == 201
    assert resp.headers.get("Idempotency-Store-Unavailable") == "true"


async def test_get_request_skips_idempotency(fresh_store: MagicMock) -> None:
    """GET requests should bypass idempotency logic entirely."""
    app = _make_app(fresh_store)

    @app.get("/some/get")
    async def get_endpoint() -> JSONResponse:
        return JSONResponse({"data": "ok"})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/some/get")

    assert resp.status_code == 200
    fresh_store.acquire.assert_not_awaited()


async def test_store_resolved_from_app_state() -> None:
    """Middleware with store=None should lazily resolve from app.state."""
    app = FastAPI()
    context = InitContext(
        app=app,
        store=None,  # No store at registration time
        required_paths=_REQUIRED_PATHS,
    )
    app.add_middleware(IdempotencyMiddleware, context=context)

    @app.post(REQUIRED_PATH)
    async def create_blog() -> JSONResponse:
        return JSONResponse({"created": True}, status_code=201)

    # Inject store into app.state (simulating lifespan init)
    store = _make_store(acquire_return=None)
    app.state.idempotency_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            REQUIRED_PATH,
            json={"title": "Hello"},
            headers={"Idempotency-Key": VALID_UUID},
        )

    assert resp.status_code == 201
    store.acquire.assert_awaited_once()


async def test_no_store_in_app_state_fails_open() -> None:
    """If store=None and app.state has no store, request should proceed (fail-open)."""
    app = FastAPI()
    context = InitContext(
        app=app,
        store=None,
        required_paths=_REQUIRED_PATHS,
    )
    app.add_middleware(IdempotencyMiddleware, context=context)

    @app.post(REQUIRED_PATH)
    async def create_blog() -> JSONResponse:
        return JSONResponse({"created": True}, status_code=201)

    # No store in app.state
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            REQUIRED_PATH,
            json={"title": "Hello"},
            headers={"Idempotency-Key": VALID_UUID},
        )

    assert resp.status_code == 201
    assert resp.headers.get("Idempotency-Store-Unavailable") == "true"


async def test_failed_state_returns_409_with_retry_after() -> None:
    """A key in 'failed' state should return 409 with a Retry-After header."""
    existing = {"status": "failed"}
    store = _make_store(acquire_return=existing)
    app = _make_app(store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            REQUIRED_PATH,
            json={"title": "Hello"},
            headers={"Idempotency-Key": VALID_UUID},
        )

    assert resp.status_code == 409
    assert resp.json()["error"] == "request_failed"
    assert resp.headers.get("Retry-After") is not None
