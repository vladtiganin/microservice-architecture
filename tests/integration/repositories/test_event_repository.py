import pytest

from main_service.models.job_models import JobEvent, Job
from main_service.repositories.event_repository import EventRepository
from main_service.repositories.jobs_repository import JobsRepository
from main_service.schemas.enums import JobEventType, JobStatus
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


@pytest.mark.asyncio
async def test_event_repository_add_persists_event(session):
    event_repo = EventRepository()
    job_repo = JobsRepository()

    job = Job(
        type="email",
        status=JobStatus.PENDING,
        payload="hello",
        result=None,
        error=None,
    ) 
    job = await job_repo.add(job, session)

    eve = JobEvent(
        job_id = job.id,
        event_type = JobEventType.CREATED,
        sequence_no = 1,
        payload = {"type" : job.type},
    )
    eve = await event_repo.add(eve, session)

    assert eve.id is not None
    assert eve.job_id == job.id
    assert eve.sequence_no == 1
    assert eve.event_type == JobEventType.CREATED


@pytest.mark.asyncio
async def test_event_repository_add_persists_payload(session):
    event_repo = EventRepository()
    job_repo = JobsRepository()

    job = Job(
        type="email",
        status=JobStatus.PENDING,
        payload="hello",
        result=None,
        error=None,
    ) 
    job = await job_repo.add(job, session)

    eve = JobEvent(
        job_id = job.id,
        event_type = JobEventType.CREATED,
        sequence_no = 1,
        payload = {"type" : job.type},
    )
    eve = await event_repo.add(eve, session)

    statement = select(JobEvent).where(JobEvent.id == 1)
    res = await session.execute(statement)
    res = res.scalar_one_or_none()

    assert res.payload == {"type" : "email"}


@pytest.mark.asyncio
async def test_event_repository_add_allows_multiple_events_for_same_job_with_different_sequence(session):
    event_repo = EventRepository()
    job_repo = JobsRepository()

    job = Job(
        type="email",
        status=JobStatus.PENDING,
        payload="hello",
        result=None,
        error=None,
    ) 
    job = await job_repo.add(job, session)

    eve_1 = JobEvent(
        job_id = job.id,
        event_type = JobEventType.CREATED,
        sequence_no = 1,
        payload = {"type" : job.type},
    )
    eve_2 = JobEvent(
        job_id = job.id,
        event_type = JobEventType.CREATED,
        sequence_no = 2,
        payload = {"type" : job.type},
    )

    eve_1 = await event_repo.add(eve_1, session)
    eve_2 = await event_repo.add(eve_2, session)

    statement = select(JobEvent).order_by(JobEvent.sequence_no)
    res = await session.execute(statement)
    res = res.scalars().all()

    seques = [eve.sequence_no for eve in res]

    assert seques == [1, 2]


@pytest.mark.asyncio
async def test_event_repository_add_raises_integrity_error_for_duplicate_sequence_no_per_job(session):
    event_repo = EventRepository()
    job_repo = JobsRepository()

    job = Job(
        type="email",
        status=JobStatus.PENDING,
        payload="hello",
        result=None,
        error=None,
    ) 
    job = await job_repo.add(job, session)

    eve_1 = JobEvent(
        job_id = job.id,
        event_type = JobEventType.CREATED,
        sequence_no = 1,
        payload = {"type" : job.type},
    )
    eve_2 = JobEvent(
        job_id = job.id,
        event_type = JobEventType.CREATED,
        sequence_no = 1,
        payload = {"type" : job.type},
    )

    eve_1 = await event_repo.add(eve_1, session)

    with pytest.raises(IntegrityError):
        eve_2 = await event_repo.add(eve_2, session)


@pytest.mark.asyncio
async def test_event_repository_add_allows_same_sequence_no_for_different_jobs(session):
    event_repo = EventRepository()
    job_repo = JobsRepository()

    job_1 = Job(
        type="email",
        status=JobStatus.PENDING,
        payload="hello",
        result=None,
        error=None,
    )
    job_2 = Job(
        type="email",
        status=JobStatus.PENDING,
        payload="hello",
        result=None,
        error=None,
    ) 
    job_1 = await job_repo.add(job_1, session)
    job_2 = await job_repo.add(job_2, session)

    eve_1 = JobEvent(
        job_id = job_1.id,
        event_type = JobEventType.CREATED,
        sequence_no = 1,
        payload = {"type" : job_1.type},
    )
    eve_2 = JobEvent(
        job_id = job_2.id,
        event_type = JobEventType.CREATED,
        sequence_no = 1,
        payload = {"type" : job_2.type},
    )

    eve_1 = await event_repo.add(eve_1, session)
    eve_2 = await event_repo.add(eve_2, session)

    statement = select(JobEvent).order_by(JobEvent.sequence_no)
    res = await session.execute(statement)
    res = res.scalars().all()

    seques = [[eve.job_id, eve.sequence_no] for eve in res]

    assert seques == [[1, 1], [2, 1]]

