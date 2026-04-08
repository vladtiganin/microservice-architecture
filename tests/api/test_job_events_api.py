from unittest.mock import ANY, AsyncMock, Mock

import httpx
import pytest
import pytest_asyncio

from main_service.api import dependencies
from main_service.main import app


@pytest_asyncio.fixture
async def simple_async_client():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://jobs",
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_get_job_events_returns_items_and_passes_pagination(
    simple_async_client: httpx.AsyncClient,
):
    service_mock = Mock()
    service_mock.get_job_events_by_id = AsyncMock(
        return_value={
            "items": [
                {
                    "id": 3,
                    "job_id": 7,
                    "event_type": "queued",
                    "sequence_no": 2,
                    "payload": {"time": "2026-04-08T12:00:00"},
                    "created_at": "2026-04-08T12:00:01",
                }
            ]
        }
    )
    app.dependency_overrides[dependencies.create_job_service_instance] = (
        lambda: service_mock
    )

    try:
        response = await simple_async_client.get("/jobs/7/events?skip=1&limit=5")
    finally:
        app.dependency_overrides.clear()

    service_mock.get_job_events_by_id.assert_awaited_once_with(
        job_id=7,
        skip=1,
        limit=5,
        session=ANY,
    )
    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": 3,
                "job_id": 7,
                "event_type": "queued",
                "sequence_no": 2,
                "payload": {"time": "2026-04-08T12:00:00"},
                "created_at": "2026-04-08T12:00:01",
            }
        ]
    }


@pytest.mark.asyncio
async def test_get_job_events_stream_uses_last_event_id_and_streams_sse(
    simple_async_client: httpx.AsyncClient,
):
    async def event_stream():
        yield 'id: 3\nevent: finished\ndata: {"id": 3, "sequence_no": 3}\n\n'

    service_mock = Mock()
    service_mock.generate_sse_job_event_stream = Mock(return_value=event_stream())
    app.dependency_overrides[dependencies.create_job_service_instance] = (
        lambda: service_mock
    )

    try:
        async with simple_async_client.stream(
            "GET",
            "/jobs/7/events/stream",
            headers={"last-event-id": "2"},
        ) as response:
            chunks = [chunk async for chunk in response.aiter_text()]
    finally:
        app.dependency_overrides.clear()

    service_mock.generate_sse_job_event_stream.assert_called_once()
    called_job_id, _, called_last_event_id = (
        service_mock.generate_sse_job_event_stream.call_args.args
    )

    assert called_job_id == 7
    assert called_last_event_id == 2
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["connection"] == "keep-alive"
    assert "".join(chunks) == 'id: 3\nevent: finished\ndata: {"id": 3, "sequence_no": 3}\n\n'
