from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from api.app import app


@pytest.fixture(name="client")
async def client_fixture() -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://vk-jug-test.hr:8000/api/v1",
    ) as client:
        yield client
