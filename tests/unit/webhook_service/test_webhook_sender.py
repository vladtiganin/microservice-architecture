import asyncio
import hmac
import json
from datetime import datetime, timezone
from hashlib import sha256
from unittest.mock import AsyncMock, Mock

import grpc
import httpx
import pytest

from contracts import webhook_pb2
from webhook_service import webhook as webhook_module
from webhook_service.webhook import WebhookSender


class AbortCalled(Exception):
    pass


class FakeContext:
    def __init__(self):
        self.abort = AsyncMock(side_effect=AbortCalled("aborted"))


class AsyncClientContext:
    def __init__(self, client):
        self.client = client

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, exc_type, exc, tb):
        return False


def build_request(target_url="https://example.com/hook", finished_at=None):
    payload = webhook_pb2.WebhookPayload(job_id=7, job_status="succeeded")
    if finished_at is not None:
        payload.finished_at.FromDatetime(finished_at)

    return webhook_pb2.SendWebhookRequest(
        webhook_id=3,
        target_url=target_url,
        payload=payload,
        secret="topsecret",
    )


@pytest.mark.asyncio
async def test_send_webhook_aborts_when_target_url_is_missing():
    sender = WebhookSender()
    context = FakeContext()
    request = build_request(target_url="")

    with pytest.raises(AbortCalled, match="aborted"):
        await sender.SendWebhook(request, context)

    context.abort.assert_awaited_once_with(
        grpc.StatusCode.INVALID_ARGUMENT,
        "target_url is required",
    )


@pytest.mark.asyncio
async def test_send_webhook_signs_and_sends_serialized_payload(monkeypatch):
    sender = WebhookSender()
    client = Mock()
    client.post = AsyncMock(return_value=Mock(status_code=200))
    finished_at = datetime(2026, 4, 13, 12, 0, tzinfo=timezone.utc)
    request = build_request(finished_at=finished_at)

    monkeypatch.setattr(
        webhook_module.httpx,
        "AsyncClient",
        lambda: AsyncClientContext(client),
    )

    response = await sender.SendWebhook(request, FakeContext())

    post_kwargs = client.post.await_args.kwargs
    expected_body = json.dumps(
        {
            "job_id": 7,
            "status": "succeeded",
            "finished_at": "2026-04-13T12:00:00Z",
        },
        separators=(",", ":"),
    ).encode()
    expected_signature = hmac.new(
        key=b"topsecret",
        msg=expected_body,
        digestmod=sha256,
    ).hexdigest()

    assert response.webhook_id == 3
    assert response.status == "sent"
    assert response.error == ""
    assert post_kwargs["url"] == "https://example.com/hook"
    assert post_kwargs["content"] == expected_body
    assert post_kwargs["headers"]["X-Webhook-Signature"] == expected_signature


@pytest.mark.asyncio
async def test_send_webhook_retries_server_errors_until_success(monkeypatch):
    sender = WebhookSender()
    client = Mock()
    client.post = AsyncMock(
        side_effect=[
            Mock(status_code=500),
            Mock(status_code=502),
            Mock(status_code=200),
        ]
    )
    sleep_mock = AsyncMock()

    monkeypatch.setattr(
        webhook_module.httpx,
        "AsyncClient",
        lambda: AsyncClientContext(client),
    )
    monkeypatch.setattr(webhook_module.asyncio, "sleep", sleep_mock)

    response = await sender.SendWebhook(build_request(), FakeContext())

    assert response.status == "sent"
    assert response.error == "server error: 502"
    assert client.post.await_count == 3
    assert [call.args[0] for call in sleep_mock.await_args_list] == [1, 2]


@pytest.mark.asyncio
async def test_send_webhook_stops_on_client_error(monkeypatch):
    sender = WebhookSender()
    client = Mock()
    client.post = AsyncMock(return_value=Mock(status_code=400, text="bad request"))

    monkeypatch.setattr(
        webhook_module.httpx,
        "AsyncClient",
        lambda: AsyncClientContext(client),
    )

    response = await sender.SendWebhook(build_request(), FakeContext())

    assert response.status == "failed"
    assert response.error == "client error 400: bad request"
    assert client.post.await_count == 1


@pytest.mark.asyncio
async def test_send_webhook_returns_failed_after_timeout_and_request_errors(monkeypatch):
    sender = WebhookSender()
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
    sleep_mock = AsyncMock()

    monkeypatch.setattr(
        webhook_module.httpx,
        "AsyncClient",
        lambda: AsyncClientContext(client),
    )
    monkeypatch.setattr(webhook_module.asyncio, "sleep", sleep_mock)

    response = await sender.SendWebhook(build_request(), FakeContext())

    assert response.status == "failed"
    assert response.error == "Request error: still down"
    assert client.post.await_count == 4
    assert [call.args[0] for call in sleep_mock.await_args_list] == [1, 2, 4]


@pytest.mark.asyncio
async def test_serve_starts_grpc_server(monkeypatch):
    server = Mock()
    server.add_insecure_port = Mock()
    server.start = AsyncMock()
    server.wait_for_termination = AsyncMock(return_value=None)
    add_servicer = Mock()

    monkeypatch.setattr(webhook_module.grpc.aio, "server", lambda: server)
    monkeypatch.setattr(
        webhook_module.webhook_pb2_grpc,
        "add_WebhookSenderServicer_to_server",
        add_servicer,
    )

    await webhook_module.serve()

    add_servicer.assert_called_once()
    servicer, registered_server = add_servicer.call_args.args
    assert isinstance(servicer, WebhookSender)
    assert registered_server is server
    server.add_insecure_port.assert_called_once_with("[::]:2121")
    server.start.assert_awaited_once()
    server.wait_for_termination.assert_awaited_once()
