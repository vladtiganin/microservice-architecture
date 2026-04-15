import hmac
from datetime import datetime, timezone
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import HTTPException

from main_service.schemas.enums import JobStatus, WebhookDeliveryStatus
from main_service.schemas.webhook_schemas import CreateWebhookRequest
from main_service.services import webhook_service as webhook_service_module
from main_service.services.webhook_service import WebhookService


class SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class SessionFactory:
    def __init__(self, *sessions):
        self.sessions = list(sessions)

    def __call__(self):
        return SessionContext(self.sessions.pop(0))


class AsyncClientContext:
    def __init__(self, client):
        self.client = client

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_create_webhook_persists_subscription_and_commits(monkeypatch):
    job_repo = Mock()
    job_repo.job_exist = AsyncMock(return_value=True)
    webhook_repo = Mock()
    session = AsyncMock()
    service = WebhookService(job_repo=job_repo, webhook_repo=webhook_repo)

    def save_webhook(webhook, _session):
        webhook.id = 3
        return webhook

    webhook_repo.add = AsyncMock(side_effect=save_webhook)
    monkeypatch.setattr(webhook_service_module.secrets, "token_hex", lambda _: "secret-token")

    result = await service.create_webhook(
        CreateWebhookRequest(job_id=7, target_url="https://example.com/hook"),
        session,
    )

    created_webhook = webhook_repo.add.await_args.args[0]

    assert created_webhook.job_id == 7
    assert created_webhook.target_url == "https://example.com/hook"
    assert created_webhook.secret == "secret-token"
    assert created_webhook.is_active is True
    assert result.id == 3
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_create_webhook_raises_404_when_job_is_missing():
    job_repo = Mock()
    job_repo.job_exist = AsyncMock(return_value=False)
    webhook_repo = Mock()
    session = AsyncMock()
    service = WebhookService(job_repo=job_repo, webhook_repo=webhook_repo)

    with pytest.raises(HTTPException) as exc_info:
        await service.create_webhook(
            CreateWebhookRequest(job_id=7, target_url="https://example.com/hook"),
            session,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Job with this id not found"


@pytest.mark.asyncio
async def test_create_webhook_rolls_back_and_raises_500_on_repository_error():
    job_repo = Mock()
    job_repo.job_exist = AsyncMock(return_value=True)
    webhook_repo = Mock()
    webhook_repo.add = AsyncMock(side_effect=Exception("db error"))
    session = AsyncMock()
    service = WebhookService(job_repo=job_repo, webhook_repo=webhook_repo)

    with pytest.raises(HTTPException) as exc_info:
        await service.create_webhook(
            CreateWebhookRequest(job_id=7, target_url="https://example.com/hook"),
            session,
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Server error, try later"
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_by_id_removes_webhook_when_it_exists():
    job_repo = Mock()
    webhook_repo = Mock()
    webhook_repo.webhook_exist = AsyncMock(return_value=True)
    webhook_repo.delete = AsyncMock()
    session = AsyncMock()
    service = WebhookService(job_repo=job_repo, webhook_repo=webhook_repo)

    result = await service.delete_by_id(4, session)

    webhook_repo.delete.assert_awaited_once_with(4, session)
    assert result == {"id": 4, "result": "Webhook deleted"}


@pytest.mark.asyncio
async def test_delete_by_id_raises_404_when_webhook_is_missing():
    job_repo = Mock()
    webhook_repo = Mock()
    webhook_repo.webhook_exist = AsyncMock(return_value=False)
    session = AsyncMock()
    service = WebhookService(job_repo=job_repo, webhook_repo=webhook_repo)

    with pytest.raises(HTTPException) as exc_info:
        await service.delete_by_id(4, session)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Webhook does not exists"


@pytest.mark.asyncio
async def test_dispatch_job_event_processes_active_webhooks_and_updates_results(monkeypatch):
    job_repo = Mock()
    webhook_repo = Mock()
    first_session = AsyncMock()
    second_session = AsyncMock()
    client = Mock()
    job = SimpleNamespace(
        id=7,
        status=JobStatus.SUCCEEDED,
        finished_at=datetime(2026, 4, 13, 12, 0, tzinfo=timezone.utc),
    )
    active_success = SimpleNamespace(id=1, is_active=True)
    inactive_webhook = SimpleNamespace(id=2, is_active=False)
    active_failed = SimpleNamespace(id=3, is_active=True)

    job_repo.find_job_by_id = AsyncMock(return_value=job)
    webhook_repo.find_wbhooks_by_job_id = AsyncMock(
        return_value=[active_success, inactive_webhook, active_failed]
    )
    webhook_repo.update_result_fields = AsyncMock()

    service = WebhookService(job_repo=job_repo, webhook_repo=webhook_repo)
    service.deliver = AsyncMock(
        side_effect=[
            {"id": 1, "success": True, "status_code": 200, "error": None},
            {"id": 3, "success": False, "status_code": 500, "error": "server error: 500"},
        ]
    )

    monkeypatch.setattr(
        webhook_service_module,
        "AsyncSessionLocal",
        SessionFactory(first_session, second_session),
    )
    monkeypatch.setattr(
        webhook_service_module.httpx,
        "AsyncClient",
        lambda: AsyncClientContext(client),
    )

    await service.dispatch_job_event(7)

    assert service.deliver.await_count == 2
    first_payload = service.deliver.await_args_list[0].args[2]
    second_payload = service.deliver.await_args_list[1].args[2]
    assert first_payload["job_id"] == 7
    assert first_payload["status"] == JobStatus.SUCCEEDED
    assert first_payload["finished_at"] == job.finished_at
    assert "timestamp" in first_payload
    assert second_payload["job_id"] == 7
    webhook_repo.update_result_fields.assert_any_await(
        error=None,
        id=1,
        session=second_session,
        status=WebhookDeliveryStatus.SENT,
    )
    webhook_repo.update_result_fields.assert_any_await(
        error="server error: 500",
        id=3,
        session=second_session,
        status=WebhookDeliveryStatus.FAILED,
    )
    second_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_job_event_returns_when_job_is_missing(monkeypatch):
    job_repo = Mock()
    webhook_repo = Mock()
    session = AsyncMock()
    job_repo.find_job_by_id = AsyncMock(return_value=None)
    webhook_repo.find_wbhooks_by_job_id = AsyncMock(return_value=[])
    service = WebhookService(job_repo=job_repo, webhook_repo=webhook_repo)
    service.deliver = AsyncMock()

    monkeypatch.setattr(
        webhook_service_module,
        "AsyncSessionLocal",
        SessionFactory(session),
    )

    await service.dispatch_job_event(7)

    service.deliver.assert_not_awaited()


@pytest.mark.asyncio
async def test_deliver_returns_success_for_2xx_response():
    service = WebhookService(job_repo=Mock(), webhook_repo=Mock())
    client = Mock()
    client.post = AsyncMock(return_value=Mock(status_code=200))
    webhook = SimpleNamespace(
        id=1,
        target_url="https://example.com/hook",
        secret="topsecret",
    )
    payload = {"job_id": 1, "status": "succeeded"}

    result = await service.deliver(webhook, client, payload)

    post_kwargs = client.post.await_args.kwargs
    expected_signature = hmac.new(
        key=b"topsecret",
        msg=post_kwargs["content"],
        digestmod=sha256,
    ).hexdigest()

    assert result == {"id": 1, "success": True, "status_code": 200, "error": None}
    assert post_kwargs["url"] == "https://example.com/hook"
    assert post_kwargs["content"] == b'{"job_id":1,"status":"succeeded"}'
    assert post_kwargs["headers"]["X-Webhook-Signature"] == expected_signature


@pytest.mark.asyncio
async def test_deliver_retries_server_errors_until_success(monkeypatch):
    service = WebhookService(job_repo=Mock(), webhook_repo=Mock())
    client = Mock()
    client.post = AsyncMock(
        side_effect=[
            Mock(status_code=500),
            Mock(status_code=502),
            Mock(status_code=201),
        ]
    )
    webhook = SimpleNamespace(
        id=1,
        target_url="https://example.com/hook",
        secret="topsecret",
    )
    sleep_mock = AsyncMock()

    monkeypatch.setattr(webhook_service_module.asyncio, "sleep", sleep_mock)

    result = await service.deliver(webhook, client, {"job_id": 1})

    assert result["success"] is True
    assert result["status_code"] == 201
    assert client.post.await_count == 3
    assert [call.args[0] for call in sleep_mock.await_args_list] == [1, 2]


@pytest.mark.asyncio
async def test_deliver_stops_on_client_error():
    service = WebhookService(job_repo=Mock(), webhook_repo=Mock())
    client = Mock()
    client.post = AsyncMock(return_value=Mock(status_code=400, text="bad request"))
    webhook = SimpleNamespace(
        id=1,
        target_url="https://example.com/hook",
        secret="topsecret",
    )

    result = await service.deliver(webhook, client, {"job_id": 1})

    assert result == {
        "id": 1,
        "success": False,
        "status_code": 400,
        "error": "client error 400: bad request",
    }
    assert client.post.await_count == 1


@pytest.mark.asyncio
async def test_deliver_returns_failure_after_timeout_and_request_errors(monkeypatch):
    service = WebhookService(job_repo=Mock(), webhook_repo=Mock())
    client = Mock()
    request = httpx.Request("POST", "https://example.com/hook")
    client.post = AsyncMock(
        side_effect=[
            httpx.TimeoutException("timeout"),
            httpx.RequestError("network down", request=request),
            httpx.TimeoutException("timeout"),
            httpx.RequestError("still down", request=request),
        ]
    )
    webhook = SimpleNamespace(
        id=1,
        target_url="https://example.com/hook",
        secret="topsecret",
    )
    sleep_mock = AsyncMock()

    monkeypatch.setattr(webhook_service_module.asyncio, "sleep", sleep_mock)

    result = await service.deliver(webhook, client, {"job_id": 1})

    assert result["id"] == 1
    assert result["success"] is False
    assert result["status_code"] is None
    assert result["error"] == "Request error: still down"
    assert client.post.await_count == 4
    assert [call.args[0] for call in sleep_mock.await_args_list] == [1, 2, 4]
