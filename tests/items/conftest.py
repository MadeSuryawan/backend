from collections.abc import AsyncGenerator

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from pytest import fixture

from app.main import app
from app.managers.rate_limiter import limiter


@fixture
async def client() -> AsyncGenerator[AsyncClient]:
    limiter.enabled = False
    async with (
        LifespanManager(app),
        AsyncClient(base_url="http://test", transport=ASGITransport(app=app)) as ac,
    ):
        yield ac
