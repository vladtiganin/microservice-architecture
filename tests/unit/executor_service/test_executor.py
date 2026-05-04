import asyncio
import json
import logging
from contextlib import contextmanager
from io import StringIO
from unittest.mock import AsyncMock, Mock

import grpc
import pytest

from contracts import executor_pb2
from executor_service import executor as executor_module
from executor_service.executor import Executor
from executor_service.core.logging.logging import JsonFormatter, ServiceFilter


class AbortCalled(Exception):
    pass


class FakeContext:
    def __init__(self, cancelled=False):
        self.abort = AsyncMock(side_effect=AbortCalled("aborted"))
        self.cancelled = Mock(return_value=cancelled)

    def invocation_metadata(self):
        return (("x-correlation-id", "test-correlation-id"),)


def parse_json_logs(stderr: str) -> list[dict]:
    return [json.loads(line) for line in stderr.splitlines() if line.strip()]


@contextmanager
def capture_structured_logs():
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ServiceFilter("executor_service"))
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    try:
        yield lambda: parse_json_logs(stream.getvalue())
    finally:
        root_logger.removeHandler(handler)
        handler.close()


@pytest.mark.asyncio
async def test_execute_job_aborts_when_job_id_is_missing():
    context = FakeContext()
    request = executor_pb2.ExecuteJobRequest(job_id=0, type="email", payload="hello")
    stream = Executor().ExecuteJob(request, context)

    with pytest.raises(AbortCalled, match="aborted"):
        await anext(stream)

    context.abort.assert_awaited_once_with(
        grpc.StatusCode.INVALID_ARGUMENT,
        "job_id required",
    )


@pytest.mark.asyncio
async def test_execute_job_aborts_when_type_is_missing():
    context = FakeContext()
    request = executor_pb2.ExecuteJobRequest(job_id=7, type="", payload="hello")
    stream = Executor().ExecuteJob(request, context)

    with pytest.raises(AbortCalled, match="aborted"):
        await anext(stream)

    context.abort.assert_awaited_once_with(
        grpc.StatusCode.INVALID_ARGUMENT,
        "job_type required",
    )


@pytest.mark.asyncio
async def test_execute_job_streams_progress_and_completion(monkeypatch):
    async def fast_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(executor_module.asyncio, "sleep", fast_sleep)

    context = FakeContext()
    request = executor_pb2.ExecuteJobRequest(job_id=7, type="email", payload="hello")
    with capture_structured_logs() as get_logs:
        responses = [response async for response in Executor().ExecuteJob(request, context)]
    logs = get_logs()

    assert [response.progress for response in responses] == [10, 30, 50, 90, 100]
    assert [response.status for response in responses] == [
        "running",
        "running",
        "running",
        "running",
        "finished",
    ]
    assert responses[-1].result == "job completed successfully"
    assert [record["event"] for record in logs] == [
        "job_execution_request_received",
        "job_execution_started",
        "job_execution_completed",
    ]
    assert all(record["service"] == "executor_service" for record in logs)
    assert all("payload" not in record for record in logs)


@pytest.mark.asyncio
async def test_execute_job_reraises_cancelled_error(monkeypatch):
    sleep_mock = AsyncMock(side_effect=asyncio.CancelledError())
    monkeypatch.setattr(executor_module.asyncio, "sleep", sleep_mock)

    context = FakeContext()
    request = executor_pb2.ExecuteJobRequest(job_id=7, type="email", payload="hello")
    stream = Executor().ExecuteJob(request, context)

    with pytest.raises(asyncio.CancelledError):
        await anext(stream)


@pytest.mark.asyncio
async def test_execute_job_yields_failed_response_on_unexpected_error(monkeypatch):
    sleep_mock = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(executor_module.asyncio, "sleep", sleep_mock)

    context = FakeContext(cancelled=False)
    request = executor_pb2.ExecuteJobRequest(job_id=7, type="email", payload="hello")
    with capture_structured_logs() as get_logs:
        responses = [response async for response in Executor().ExecuteJob(request, context)]
    logs = get_logs()

    assert len(responses) == 1
    assert responses[0].status == "failed"
    assert responses[0].error == "Something goes wrong during execution"
    assert [record["event"] for record in logs] == [
        "job_execution_request_received",
        "job_execution_started",
        "job_execution_failed",
    ]
    assert logs[-1]["error_type"] == "RuntimeError"
    assert logs[-1]["error_message"] == "boom"


@pytest.mark.asyncio
async def test_serve_starts_grpc_server(monkeypatch):
    server = Mock()
    server.add_insecure_port = Mock()
    server.start = AsyncMock()
    server.wait_for_termination = AsyncMock(return_value=None)
    add_servicer = Mock()

    monkeypatch.setattr(executor_module.grpc.aio, "server", lambda: server)
    monkeypatch.setattr(
        executor_module.executor_pb2_grpc,
        "add_ExecutorServicer_to_server",
        add_servicer,
    )

    await executor_module.serve()

    add_servicer.assert_called_once()
    servicer, registered_server = add_servicer.call_args.args
    assert isinstance(servicer, Executor)
    assert registered_server is server
    server.add_insecure_port.assert_called_once_with("[::]:4343")
    server.start.assert_awaited_once()
    server.wait_for_termination.assert_awaited_once()
