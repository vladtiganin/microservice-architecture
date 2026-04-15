import pytest
from unittest.mock import AsyncMock
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from main_service.models.job_models import JobEvent
from main_service.repositories.event_repository import EventRepository
from main_service.repositories.jobs_repository import JobsRepository
from main_service.schemas.enums import JobEventType, JobStatus
from main_service.schemas.jobs_schemas import CreateJobRequest
from main_service.services.job_executor import JobExecutor
from main_service.services.job_service import JobService
from main_service.services import job_executor as job_executor_module
from main_service.services import job_service as jobs_services_module
from main_service.services import transition as transition_module


class StubExecutor:
    async def run_job(self, job_id: int) -> None:
        return None


class StubWebhookService:
    def __init__(self):
        self.dispatch_job_event = AsyncMock()


def _patch_test_sessionmakers(monkeypatch, engine):
    session_local = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    monkeypatch.setattr(transition_module, "AsyncSessionLocal", session_local)
    monkeypatch.setattr(job_executor_module, "AsyncSessionLocal", session_local)
    return session_local


def _disable_background_task(monkeypatch):
    def fake_create_task(coro):
        coro.close()
        return None

    monkeypatch.setattr(jobs_services_module, "create_task", fake_create_task)


@pytest.mark.asyncio
async def test_create_job_moves_job_to_queued_and_writes_created_and_queued_events(session, engine, monkeypatch):
    session_local = _patch_test_sessionmakers(monkeypatch, engine)
    _disable_background_task(monkeypatch)

    job_repo = JobsRepository()
    event_repo = EventRepository()
    service = JobService(job_repo=job_repo, event_repo=event_repo, job_executor=StubExecutor())

    created_job = await service.create_job(
        CreateJobRequest(type="email", payload="hello"),
        session,
    )

    async with session_local() as check_session:
        job_from_db = await job_repo.find_job_by_id(created_job.id, check_session)
        events = (
            await check_session.execute(
                select(JobEvent)
                .where(JobEvent.job_id == created_job.id)
                .order_by(JobEvent.sequence_no)
            )
        ).scalars().all()

    assert job_from_db is not None
    assert job_from_db.status == JobStatus.QUEUED
    assert [event.event_type for event in events] == [
        JobEventType.CREATED,
        JobEventType.QUEUED,
    ]
    assert events[1].payload["time"]


@pytest.mark.asyncio
async def test_job_executor_completes_lifecycle_and_persists_progress_events(session, engine, monkeypatch):
    session_local = _patch_test_sessionmakers(monkeypatch, engine)
    _disable_background_task(monkeypatch)

    async def fast_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(job_executor_module.asyncio, "sleep", fast_sleep)

    job_repo = JobsRepository()
    event_repo = EventRepository()
    service = JobService(job_repo=job_repo, event_repo=event_repo, job_executor=StubExecutor())
    webhook_service = StubWebhookService()
    executor = JobExecutor(
        job_repo=job_repo,
        event_repo=event_repo,
        webhook_service=webhook_service,
    )

    created_job = await service.create_job(
        CreateJobRequest(type="email", payload="hello"),
        session,
    )
    
    await executor.run_job(created_job.id)

    async with session_local() as check_session:
        job_from_db = await job_repo.find_job_by_id(created_job.id, check_session)
        events = (
            await check_session.execute(
                select(JobEvent)
                .where(JobEvent.job_id == created_job.id)
                .order_by(JobEvent.sequence_no)
            )
        ).scalars().all()

    assert job_from_db is not None
    assert job_from_db.status == JobStatus.SUCCEEDED
    assert job_from_db.result == "hello"
    assert job_from_db.started_at is not None
    assert job_from_db.finished_at is not None
    assert [event.event_type for event in events] == [
        JobEventType.CREATED,
        JobEventType.QUEUED,
        JobEventType.STARTED,
        JobEventType.RUNNING,
        JobEventType.RUNNING,
        JobEventType.FINISHED,
    ]
    assert events[-1].payload == {"progress": "100%"}
    webhook_service.dispatch_job_event.assert_awaited_once_with(job_id=created_job.id)
