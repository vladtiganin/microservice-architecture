import hmac
import json
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import HTTPException

from contracts import webhook_pb2
from main_service.schemas.enums import JobStatus, WebhookDeliveryStatus
from main_service.schemas.webhook_schemas import CreateWebhookRequest
from main_service.services import webhook_service as webhook_service_module
from main_service.services.webhook_service import WebhookService
from main_service.core.logging.logging import JsonFormatter, ServiceFilter


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


def parse_json_logs(stderr: str) -> list[dict]:
    return [json.loads(line) for line in stderr.splitlines() if line.strip()]


@contextmanager
def capture_structured_logs():
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ServiceFilter("main_service"))
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    try:
        yield lambda: parse_json_logs(stream.getvalue())
    finally:
        root_logger.removeHandler(handler)
        handler.close()


@pytest.fixture
def webhook_service_fixture():
    job_repo = Mock()
    webhook_repo = Mock()
    webhook_sender = Mock()
    webhook_sender.SendWebhook = AsyncMock()
    service = WebhookService(
        job_repo=job_repo,
        webhook_repo=webhook_repo,
        webhook_sender=webhook_sender,
    )
    return service, job_repo, webhook_repo, webhook_sender


@pytest.mark.asyncio
async def test_create_webhook_persists_subscription_and_commits(
    webhook_service_fixture,
    monkeypatch,
):
    service, job_repo, webhook_repo, _ = webhook_service_fixture
    job_repo.job_exist = AsyncMock(return_value=True)
    session = AsyncMock()

    def save_webhook(webhook, _session):
        webhook.id = 3
        return webhook

    webhook_repo.add = AsyncMock(side_effect=save_webhook)
    monkeypatch.setattr(webhook_service_module.secrets, "token_hex", lambda _: "secret-token")

    with capture_structured_logs() as get_logs:
        result = await service.create_webhook(
            CreateWebhookRequest(job_id=7, target_url="https://example.com/hook"),
            session,
        )
    logs = get_logs()

    created_webhook = webhook_repo.add.await_args.args[0]

    assert created_webhook.job_id == 7
    assert created_webhook.target_url == "https://example.com/hook"
    assert created_webhook.secret == "secret-token"
    assert created_webhook.is_active is True
    assert result.id == 3
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(result)
    assert [record["event"] for record in logs] == ["webhook_created"]
    assert logs[0]["service"] == "main_service"
    assert "secret" not in logs[0]


@pytest.mark.asyncio
async def test_create_webhook_raises_404_when_job_is_missing(webhook_service_fixture):
    service, job_repo, _, _ = webhook_service_fixture
    job_repo.job_exist = AsyncMock(return_value=False)
    session = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await service.create_webhook(
            CreateWebhookRequest(job_id=7, target_url="https://example.com/hook"),
            session,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Job with this id not found"


@pytest.mark.asyncio
async def test_create_webhook_rolls_back_and_raises_500_on_repository_error(
    webhook_service_fixture,
):
    service, job_repo, webhook_repo, _ = webhook_service_fixture
    job_repo.job_exist = AsyncMock(return_value=True)
    webhook_repo.add = AsyncMock(side_effect=Exception("db error"))
    session = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await service.create_webhook(
            CreateWebhookRequest(job_id=7, target_url="https://example.com/hook"),
            session,
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Server error, try later"
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_by_id_removes_webhook_when_it_exists(webhook_service_fixture):
    service, _, webhook_repo, _ = webhook_service_fixture
    webhook_repo.webhook_exist = AsyncMock(return_value=True)
    webhook_repo.delete = AsyncMock()
    session = AsyncMock()

    result = await service.delete_by_id(4, session)

    webhook_repo.delete.assert_awaited_once_with(4, session)
    session.commit.assert_awaited_once()
    assert result == {"id": 4, "result": "Webhook deleted"}


@pytest.mark.asyncio
async def test_delete_by_id_raises_404_when_webhook_is_missing(webhook_service_fixture):
    service, _, webhook_repo, _ = webhook_service_fixture
    webhook_repo.webhook_exist = AsyncMock(return_value=False)
    session = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await service.delete_by_id(4, session)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Webhook does not exists"


@pytest.mark.asyncio
async def test_dispatch_job_event_sends_active_webhooks_and_updates_delivery_statuses(
    webhook_service_fixture,
    monkeypatch,
):
    service, job_repo, webhook_repo, webhook_sender = webhook_service_fixture
    first_session = AsyncMock()
    second_session = AsyncMock()
    finished_at = datetime(2026, 4, 13, 12, 0, tzinfo=timezone.utc)
    job = SimpleNamespace(id=7, status=JobStatus.SUCCEEDED, finished_at=finished_at)
    active_success = SimpleNamespace(
        id=1,
        target_url="https://example.com/a",
        secret="secret-a",
        is_active=True,
    )
    inactive_webhook = SimpleNamespace(
        id=2,
        target_url="https://example.com/b",
        secret="secret-b",
        is_active=False,
    )
    active_failed = SimpleNamespace(
        id=3,
        target_url="https://example.com/c",
        secret="secret-c",
        is_active=True,
    )

    job_repo.find_job_by_id = AsyncMock(return_value=job)
    webhook_repo.find_wbhooks_by_job_id = AsyncMock(
        return_value=[active_success, inactive_webhook, active_failed]
    )
    webhook_repo.update_result_fields = AsyncMock()
    webhook_sender.SendWebhook.side_effect = [
        webhook_pb2.SendWebhookResponse(webhook_id=1, status="sent", error=""),
        webhook_pb2.SendWebhookResponse(
            webhook_id=3,
            status="failed",
            error="server error: 500",
        ),
    ]

    monkeypatch.setattr(
        webhook_service_module,
        "AsyncSessionLocal",
        SessionFactory(first_session, second_session),
    )

    with capture_structured_logs() as get_logs:
        await service.dispatch_job_event(7)
    logs = get_logs()

    first_request = webhook_sender.SendWebhook.await_args_list[0].args[0]
    second_request = webhook_sender.SendWebhook.await_args_list[1].args[0]

    assert webhook_sender.SendWebhook.await_count == 2
    assert webhook_sender.SendWebhook.await_args_list[0].kwargs["timeout"] == 60
    assert webhook_sender.SendWebhook.await_args_list[1].kwargs["timeout"] == 60
    assert first_request.webhook_id == 1
    assert first_request.target_url == "https://example.com/a"
    assert first_request.secret == "secret-a"
    assert first_request.payload.job_id == 7
    assert first_request.payload.job_status == JobStatus.SUCCEEDED
    assert first_request.payload.HasField("finished_at") is True
    assert first_request.payload.finished_at.ToDatetime(timezone.utc) == finished_at
    assert second_request.webhook_id == 3
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
    assert [record["event"] for record in logs] == [
        "webhook_dispatch_started",
        "webhook_dispatch_result",
        "webhook_dispatch_result",
        "webhook_dispatch_completed",
    ]
    assert all("secret" not in record for record in logs)


@pytest.mark.asyncio
async def test_dispatch_job_event_ignores_sender_exceptions_and_processes_other_results(
    webhook_service_fixture,
    monkeypatch,
):
    service, job_repo, webhook_repo, webhook_sender = webhook_service_fixture
    first_session = AsyncMock()
    second_session = AsyncMock()
    job = SimpleNamespace(
        id=7,
        status=JobStatus.SUCCEEDED,
        finished_at=datetime(2026, 4, 13, 12, 0, tzinfo=timezone.utc),
    )
    first_webhook = SimpleNamespace(
        id=1,
        target_url="https://example.com/a",
        secret="secret-a",
        is_active=True,
    )
    second_webhook = SimpleNamespace(
        id=2,
        target_url="https://example.com/b",
        secret="secret-b",
        is_active=True,
    )

    job_repo.find_job_by_id = AsyncMock(return_value=job)
    webhook_repo.find_wbhooks_by_job_id = AsyncMock(
        return_value=[first_webhook, second_webhook]
    )
    webhook_repo.update_result_fields = AsyncMock()
    webhook_sender.SendWebhook.side_effect = [
        RuntimeError("sender failed"),
        webhook_pb2.SendWebhookResponse(webhook_id=2, status="sent", error=""),
    ]

    monkeypatch.setattr(
        webhook_service_module,
        "AsyncSessionLocal",
        SessionFactory(first_session, second_session),
    )

    await service.dispatch_job_event(7)

    webhook_repo.update_result_fields.assert_awaited_once_with(
        error=None,
        id=2,
        session=second_session,
        status=WebhookDeliveryStatus.SENT,
    )
    second_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_job_event_returns_when_job_is_missing(
    webhook_service_fixture,
    monkeypatch,
):
    service, job_repo, webhook_repo, webhook_sender = webhook_service_fixture
    session = AsyncMock()
    job_repo.find_job_by_id = AsyncMock(return_value=None)
    webhook_repo.find_wbhooks_by_job_id = AsyncMock(return_value=[])

    monkeypatch.setattr(
        webhook_service_module,
        "AsyncSessionLocal",
        SessionFactory(session),
    )

    await service.dispatch_job_event(7)

    webhook_sender.SendWebhook.assert_not_awaited()


@pytest.mark.asyncio
async def test_deliver_returns_success_for_2xx_response(webhook_service_fixture):
    service, _, _, _ = webhook_service_fixture
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
async def test_deliver_retries_server_errors_until_success(
    webhook_service_fixture,
    monkeypatch,
):
    service, _, _, _ = webhook_service_fixture
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
async def test_deliver_stops_on_client_error(webhook_service_fixture):
    service, _, _, _ = webhook_service_fixture
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
        "error": "client error 400",
    }
    assert client.post.await_count == 1


@pytest.mark.asyncio
async def test_deliver_returns_failure_after_timeout_and_request_errors(
    webhook_service_fixture,
    monkeypatch,
):
    service, _, _, _ = webhook_service_fixture
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
