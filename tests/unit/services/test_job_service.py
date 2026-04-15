from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from main_service.models.job_models import Job, JobEvent
from main_service.schemas.enums import JobEventType, JobStatus
from main_service.schemas.jobs_schemas import CreateJobRequest
from main_service.services import job_service as job_service_module
from main_service.services.job_service import JobService


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


@pytest.fixture
def job_service_fixture():
    job_repo = Mock()
    event_repo = Mock()
    job_executor = Mock()
    job_executor.run_job = AsyncMock()
    service = JobService(job_repo=job_repo, event_repo=event_repo, job_executor=job_executor)
    return service, job_repo, event_repo, job_executor


@pytest.mark.asyncio
async def test_get_jobs_returns_items_list(job_service_fixture):
    service, job_repo, _, _ = job_service_fixture
    job_1, job_2 = Mock(), Mock()
    job_repo.get = AsyncMock(return_value=[job_1, job_2])
    session = Mock()

    result = await service.get_jobs(session=session, skip=0, limit=10)

    job_repo.get.assert_awaited_once_with(session, 0, 10)
    assert result == {"items": [job_1, job_2]}


@pytest.mark.asyncio
async def test_create_job_creates_pending_job_created_event_and_background_work(
    job_service_fixture,
    monkeypatch,
):
    service, job_repo, event_repo, job_executor = job_service_fixture
    req = CreateJobRequest(type="email", payload="hello")
    stored_job = Job(id=1, type="email", payload="hello", status=JobStatus.PENDING)
    job_repo.add = AsyncMock(return_value=stored_job)
    event_repo.add = AsyncMock()
    session = AsyncMock()
    transition_mock = AsyncMock()
    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return Mock()

    monkeypatch.setattr(job_service_module, "transition_job", transition_mock)
    monkeypatch.setattr(job_service_module, "create_task", fake_create_task)

    result = await service.create_job(req, session)

    created_job = job_repo.add.await_args.args[0]
    created_event = event_repo.add.await_args.args[0]
    transition_kwargs = transition_mock.await_args.kwargs

    assert result is stored_job
    assert created_job.type == "email"
    assert created_job.payload == "hello"
    assert created_job.status == JobStatus.PENDING
    assert created_event.job_id == 1
    assert created_event.event_type == JobEventType.CREATED
    assert created_event.sequence_no == 1
    assert created_event.payload == {"type": "email"}
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(stored_job)
    session.rollback.assert_not_awaited()
    assert transition_kwargs["job_id"] == 1
    assert transition_kwargs["job_status"] == JobStatus.QUEUED
    assert transition_kwargs["event_type"] == JobEventType.QUEUED
    assert transition_kwargs["job_repo"] is job_repo
    assert transition_kwargs["event_repo"] is event_repo
    assert "time" in transition_kwargs["event_payload"]
    job_executor.run_job.assert_called_once_with(1)
    assert len(scheduled) == 1


@pytest.mark.asyncio
async def test_create_job_rolls_back_and_raises_500_when_job_repo_add_fails(job_service_fixture):
    service, job_repo, event_repo, _ = job_service_fixture
    job_repo.add = AsyncMock(side_effect=Exception("db error"))
    event_repo.add = AsyncMock()
    session = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await service.create_job(CreateJobRequest(type="email", payload="hello"), session)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Error during creating a job"
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
    event_repo.add.assert_not_called()


@pytest.mark.asyncio
async def test_create_job_rolls_back_and_raises_500_when_event_repo_add_fails(job_service_fixture):
    service, job_repo, event_repo, _ = job_service_fixture
    job_repo.add = AsyncMock(return_value=Job(id=1, type="email", payload="hello", status=JobStatus.PENDING))
    event_repo.add = AsyncMock(side_effect=Exception("db error"))
    session = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await service.create_job(CreateJobRequest(type="email", payload="hello"), session)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Error during creating a job"
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_job_by_id_returns_job_when_found(job_service_fixture):
    service, job_repo, _, _ = job_service_fixture
    fake_job = Mock()
    job_repo.find_job_by_id = AsyncMock(return_value=fake_job)
    session = AsyncMock()

    result = await service.get_job_by_id(1, session)

    job_repo.find_job_by_id.assert_awaited_once_with(1, session)
    assert result is fake_job


@pytest.mark.asyncio
async def test_get_job_by_id_raises_404_when_not_found(job_service_fixture):
    service, job_repo, _, _ = job_service_fixture
    job_repo.find_job_by_id = AsyncMock(return_value=None)
    session = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await service.get_job_by_id(1, session)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Job with this id not found"


@pytest.mark.asyncio
async def test_get_job_events_by_id_returns_items_from_repository(job_service_fixture):
    service, _, event_repo, _ = job_service_fixture
    first_event, second_event = Mock(), Mock()
    event_repo.get = AsyncMock(return_value=[first_event, second_event])
    session = AsyncMock()

    result = await service.get_job_events_by_id(job_id=7, session=session, skip=2, limit=3)

    event_repo.get.assert_awaited_once_with(7, session, 2, 3)
    assert result == {"items": [first_event, second_event]}


@pytest.mark.asyncio
async def test_generate_sse_job_event_stream_raises_404_when_job_does_not_exist(
    job_service_fixture,
    monkeypatch,
):
    service, job_repo, event_repo, _ = job_service_fixture
    first_session = AsyncMock()
    request = Mock()
    request.is_disconnected = AsyncMock(return_value=False)
    job_repo.job_exist = AsyncMock(return_value=False)
    event_repo.get = AsyncMock()

    monkeypatch.setattr(
        job_service_module,
        "AsyncSessionLocal",
        SessionFactory(first_session),
    )

    stream = service.generate_sse_job_event_stream(job_id=7, request=request)

    with pytest.raises(HTTPException) as exc_info:
        await anext(stream)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Job not found"
    job_repo.job_exist.assert_awaited_once_with(7, first_session)
    event_repo.get.assert_not_called()


@pytest.mark.asyncio
async def test_generate_sse_job_event_stream_yields_terminal_event_and_stops(
    job_service_fixture,
    monkeypatch,
):
    service, job_repo, event_repo, _ = job_service_fixture
    first_session = AsyncMock()
    second_session = AsyncMock()
    request = Mock()
    request.is_disconnected = AsyncMock(return_value=False)
    job_repo.job_exist = AsyncMock(return_value=True)
    terminal_event = JobEvent(
        id=3,
        job_id=7,
        event_type=JobEventType.FINISHED,
        sequence_no=3,
        payload={"progress": "100%"},
    )
    terminal_event.created_at = datetime(2026, 4, 13, 10, 0, tzinfo=timezone.utc)
    event_repo.get = AsyncMock(return_value=[terminal_event])

    monkeypatch.setattr(
        job_service_module,
        "AsyncSessionLocal",
        SessionFactory(first_session, second_session),
    )

    stream = service.generate_sse_job_event_stream(
        job_id=7,
        request=request,
        last_sse_event_id=2,
    )

    payload = await anext(stream)

    with pytest.raises(StopAsyncIteration):
        await anext(stream)

    job_repo.job_exist.assert_awaited_once_with(7, first_session)
    event_repo.get.assert_awaited_once_with(job_id=7, session=second_session, skip=2, limit=1)
    request.is_disconnected.assert_awaited_once()
    assert payload.startswith("id: 3\n")
    assert "event: JobEventType.FINISHED\n" in payload
    assert '"event_type": "finished"' in payload
