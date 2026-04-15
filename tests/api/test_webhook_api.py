from datetime import datetime, timezone
from unittest.mock import ANY, AsyncMock, Mock

import httpx
import pytest
from fastapi import HTTPException

from main_service.api import dependencies
from main_service.main import app


@pytest.mark.asyncio
async def test_post_webhook_returns_200_and_created_webhook(simple_async_client: httpx.AsyncClient):
    service_mock = Mock()
    service_mock.create_webhook = AsyncMock(
        return_value={
            "id": 5,
            "job_id": 7,
            "target_url": "https://example.com/hook",
            "secret": "secret-token",
            "created_at": datetime(2026, 4, 13, 9, 0, tzinfo=timezone.utc),
        }
    )
    app.dependency_overrides[dependencies.create_webhook_service_instance] = lambda: service_mock

    try:
        response = await simple_async_client.post(
            "/webhook",
            json={"job_id": 7, "target_url": "https://example.com/hook"},
        )
    finally:
        app.dependency_overrides.clear()

    service_mock.create_webhook.assert_awaited_once()
    call_args = service_mock.create_webhook.await_args.args
    assert call_args[0].job_id == 7
    assert str(call_args[0].target_url) == "https://example.com/hook"
    assert call_args[1] is not None
    assert response.status_code == 200
    assert response.json() == {
        "id": 5,
        "job_id": 7,
        "target_url": "https://example.com/hook",
        "secret": "secret-token",
        "created_at": "2026-04-13T09:00:00Z",
    }


@pytest.mark.asyncio
async def test_post_webhook_returns_404_when_service_raises_http_exception(
    simple_async_client: httpx.AsyncClient,
):
    service_mock = Mock()
    service_mock.create_webhook = AsyncMock(
        side_effect=HTTPException(status_code=404, detail="Job with this id not found")
    )
    app.dependency_overrides[dependencies.create_webhook_service_instance] = lambda: service_mock

    try:
        response = await simple_async_client.post(
            "/webhook",
            json={"job_id": 7, "target_url": "https://example.com/hook"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_post_webhook_returns_422_when_job_id_is_missing(simple_async_client: httpx.AsyncClient):
    response = await simple_async_client.post(
        "/webhook",
        json={"target_url": "https://example.com/hook"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_webhook_returns_422_when_target_url_is_invalid(simple_async_client: httpx.AsyncClient):
    response = await simple_async_client.post(
        "/webhook",
        json={"job_id": 7, "target_url": "not-a-url"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_delete_webhook_returns_200_and_result(simple_async_client: httpx.AsyncClient):
    service_mock = Mock()
    service_mock.delete_by_id = AsyncMock(return_value={"id": 4, "result": "Webhook deleted"})
    app.dependency_overrides[dependencies.create_webhook_service_instance] = lambda: service_mock

    try:
        response = await simple_async_client.delete("/webhook/4")
    finally:
        app.dependency_overrides.clear()

    service_mock.delete_by_id.assert_awaited_once_with(4, ANY)
    assert response.status_code == 200
    assert response.json() == {"id": 4, "result": "Webhook deleted"}


@pytest.mark.asyncio
async def test_delete_webhook_returns_404_when_service_raises_http_exception(
    simple_async_client: httpx.AsyncClient,
):
    service_mock = Mock()
    service_mock.delete_by_id = AsyncMock(
        side_effect=HTTPException(status_code=404, detail="Webhook does not exists")
    )
    app.dependency_overrides[dependencies.create_webhook_service_instance] = lambda: service_mock

    try:
        response = await simple_async_client.delete("/webhook/4")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_webhook_returns_422_for_invalid_webhook_id(simple_async_client: httpx.AsyncClient):
    response = await simple_async_client.delete("/webhook/abc")

    assert response.status_code == 422
