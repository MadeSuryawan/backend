from unittest.mock import sentinel

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from structlog.contextvars import get_contextvars

from app.context import cache_manager_ctx
from app.middleware.context import ContextMiddleware
from app.middleware.middleware import LoggingMiddleware
from app.middleware.timezone import TimezoneMiddleware


async def test_timezone_middleware_sets_state_from_header() -> None:
    app = FastAPI()
    app.add_middleware(TimezoneMiddleware)

    @app.get("/tz")
    async def get_timezone(request: Request) -> JSONResponse:
        return JSONResponse({"timezone": request.state.user_timezone})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/tz", headers={"X-Client-Timezone": "Asia/Makassar"})

    assert response.status_code == 200
    assert response.json() == {"timezone": "Asia/Makassar"}


async def test_context_middleware_sets_and_resets_cache_manager_context() -> None:
    app = FastAPI()
    app.state.cache_manager = sentinel.cache_manager
    app.add_middleware(ContextMiddleware)

    @app.get("/context")
    async def get_context() -> JSONResponse:
        return JSONResponse(
            {"has_cache_manager": cache_manager_ctx.get() is sentinel.cache_manager},
        )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/context")

    assert response.status_code == 200
    assert response.json() == {"has_cache_manager": True}
    assert cache_manager_ctx.get() is None


async def test_logging_middleware_binds_and_clears_request_id() -> None:
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.get("/logging-test", summary="Logging summary")
    async def logging_test() -> JSONResponse:
        request_id = get_contextvars().get("request_id")
        return JSONResponse(
            {"request_id_present": isinstance(request_id, str) and len(request_id) == 8},
        )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/logging-test")

    assert response.status_code == 200
    assert response.json() == {"request_id_present": True}
    assert len(response.headers["X-Request-ID"]) == 8
    assert get_contextvars().get("request_id") is None
