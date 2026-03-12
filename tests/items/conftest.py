from collections.abc import AsyncGenerator

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from pytest import fixture

from app.db import engine
from app.main import app
from app.managers.rate_limiter import limiter


@fixture
async def client() -> AsyncGenerator[AsyncClient]:
    limiter.enabled = False

    # The async engine is a global singleton and may still hold pooled
    # connections created on a previous test's event loop.
    await engine.dispose()

    async with (
        LifespanManager(app),
        AsyncClient(base_url="http://test", transport=ASGITransport(app=app)) as ac,
    ):
        yield ac
