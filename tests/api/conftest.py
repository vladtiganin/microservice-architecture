import httpx
import pytest_asyncio

from main_service.main import app


@pytest_asyncio.fixture
async def simple_async_client():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://jobs",
    ) as client:
        yield client
