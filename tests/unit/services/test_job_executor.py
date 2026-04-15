from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from main_service.schemas.enums import JobEventType, JobStatus
from main_service.services import job_executor as job_executor_module
from main_service.services.job_executor import JobExecutor


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


@pytest.mark.asyncio
async def test_run_job_returns_early_when_job_is_missing(monkeypatch):
    job_repo = Mock()
    job_repo.find_job_by_id = AsyncMock(return_value=None)
    event_repo = Mock()
    webhook_service = Mock()
    webhook_service.dispatch_job_event = AsyncMock()
    transition_mock = AsyncMock()

    monkeypatch.setattr(job_executor_module, "AsyncSessionLocal", SessionFactory(AsyncMock()))
    monkeypatch.setattr(job_executor_module, "transition_job", transition_mock)

    executor = JobExecutor(job_repo=job_repo, event_repo=event_repo, webhook_service=webhook_service)

    await executor.run_job(7)

    transition_mock.assert_not_awaited()
    webhook_service.dispatch_job_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_job_transitions_successfully_and_dispatches_webhook(monkeypatch):
    job = SimpleNamespace(id=7, payload="hello")
    job_repo = Mock()
    job_repo.find_job_by_id = AsyncMock(return_value=job)
    event_repo = Mock()
    webhook_service = Mock()
    webhook_service.dispatch_job_event = AsyncMock()
    transition_mock = AsyncMock()
    sleep_mock = AsyncMock()

    monkeypatch.setattr(job_executor_module, "AsyncSessionLocal", SessionFactory(AsyncMock()))
    monkeypatch.setattr(job_executor_module, "transition_job", transition_mock)
    monkeypatch.setattr(job_executor_module.asyncio, "sleep", sleep_mock)

    executor = JobExecutor(job_repo=job_repo, event_repo=event_repo, webhook_service=webhook_service)

    await executor.run_job(7)

    statuses = [call.kwargs["job_status"] for call in transition_mock.await_args_list]
    event_types = [call.kwargs["event_type"] for call in transition_mock.await_args_list]

    assert statuses == [
        JobStatus.RUNNING,
        JobStatus.RUNNING,
        JobStatus.RUNNING,
        JobStatus.SUCCEEDED,
    ]
    assert event_types == [
        JobEventType.STARTED,
        JobEventType.RUNNING,
        JobEventType.RUNNING,
        JobEventType.FINISHED,
    ]
    assert transition_mock.await_args_list[-1].kwargs["result"] == "hello"
    assert [call.args[0] for call in sleep_mock.await_args_list] == [1, 2, 1]
    webhook_service.dispatch_job_event.assert_awaited_once_with(job_id=7)


@pytest.mark.asyncio
async def test_run_job_marks_job_failed_when_processing_step_raises(monkeypatch):
    job = SimpleNamespace(id=7, payload="hello")
    job_repo = Mock()
    job_repo.find_job_by_id = AsyncMock(return_value=job)
    event_repo = Mock()
    webhook_service = Mock()
    webhook_service.dispatch_job_event = AsyncMock()
    transition_mock = AsyncMock(side_effect=[None, RuntimeError("boom"), None])
    sleep_mock = AsyncMock()

    monkeypatch.setattr(job_executor_module, "AsyncSessionLocal", SessionFactory(AsyncMock()))
    monkeypatch.setattr(job_executor_module, "transition_job", transition_mock)
    monkeypatch.setattr(job_executor_module.asyncio, "sleep", sleep_mock)

    executor = JobExecutor(job_repo=job_repo, event_repo=event_repo, webhook_service=webhook_service)

    await executor.run_job(7)

    assert transition_mock.await_count == 3
    assert transition_mock.await_args_list[-1].kwargs["job_status"] == JobStatus.FAILED
    assert transition_mock.await_args_list[-1].kwargs["event_type"] == JobEventType.FAILED
    assert transition_mock.await_args_list[-1].kwargs["error"] == "RuntimeError"
    webhook_service.dispatch_job_event.assert_awaited_once_with(job_id=7)
