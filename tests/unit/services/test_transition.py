from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from main_service.models.job_models import Job
from main_service.schemas.enums import JobEventType, JobStatus
from main_service.services import transition as transition_module
from main_service.services.transition import define_time_fields, transition_job


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


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalars(self):
        return self

    def first(self):
        return self.value


@pytest.mark.asyncio
async def test_transition_job_returns_none_when_job_is_missing(monkeypatch):
    job_repo = Mock()
    job_repo.find_job_by_id = AsyncMock(return_value=None)
    event_repo = Mock()
    event_repo.add = AsyncMock()
    session = AsyncMock()

    monkeypatch.setattr(
        transition_module,
        "AsyncSessionLocal",
        SessionFactory(session),
    )

    result = await transition_job(
        job_id=7,
        job_status=JobStatus.RUNNING,
        event_type=JobEventType.RUNNING,
        job_repo=job_repo,
        event_repo=event_repo,
    )

    assert result is None
    event_repo.add.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_transition_job_increments_sequence_and_uses_default_payload(monkeypatch):
    job_repo = Mock()
    job = Job(id=7, type="email", payload="hello", status=JobStatus.PENDING)
    job_repo.find_job_by_id = AsyncMock(return_value=job)
    event_repo = Mock()
    event_repo.add = AsyncMock()
    session = AsyncMock()
    session.execute = AsyncMock(return_value=ScalarResult(2))

    monkeypatch.setattr(
        transition_module,
        "AsyncSessionLocal",
        SessionFactory(session),
    )

    result = await transition_job(
        job_id=7,
        job_status=JobStatus.RUNNING,
        event_type=JobEventType.RUNNING,
        job_repo=job_repo,
        event_repo=event_repo,
    )

    created_event = event_repo.add.await_args.args[0]

    assert result is job
    assert created_event.job_id == 7
    assert created_event.sequence_no == 3
    assert created_event.event_type == JobEventType.RUNNING
    assert created_event.payload == {"job_payload": "hello"}
    assert job.started_at is not None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_transition_job_rolls_back_when_event_persist_fails(monkeypatch):
    job_repo = Mock()
    job = Job(id=7, type="email", payload="hello", status=JobStatus.PENDING)
    job_repo.find_job_by_id = AsyncMock(return_value=job)
    event_repo = Mock()
    event_repo.add = AsyncMock(side_effect=RuntimeError("db error"))
    session = AsyncMock()
    session.execute = AsyncMock(return_value=ScalarResult(None))

    monkeypatch.setattr(
        transition_module,
        "AsyncSessionLocal",
        SessionFactory(session),
    )

    with pytest.raises(RuntimeError, match="db error"):
        await transition_job(
            job_id=7,
            job_status=JobStatus.RUNNING,
            event_type=JobEventType.RUNNING,
            event_payload={"progress": "10%"},
            job_repo=job_repo,
            event_repo=event_repo,
        )

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


def test_define_time_fields_sets_started_at_for_first_running_status():
    job = Job(type="email", payload="hello", status=JobStatus.RUNNING)

    define_time_fields(job)

    assert job.started_at is not None
    assert job.updated_at is None


def test_define_time_fields_updates_updated_at_for_repeated_running_status():
    started_at = datetime(2026, 4, 13, 10, 0, tzinfo=timezone.utc)
    job = Job(type="email", payload="hello", status=JobStatus.RUNNING)
    job.started_at = started_at

    define_time_fields(job)

    assert job.started_at == started_at
    assert job.updated_at is not None


def test_define_time_fields_sets_finished_at_for_terminal_status():
    job = Job(type="email", payload="hello", status=JobStatus.SUCCEEDED)

    define_time_fields(job)

    assert job.finished_at is not None
