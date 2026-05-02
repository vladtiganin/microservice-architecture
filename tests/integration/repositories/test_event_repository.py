import pytest

from sqlalchemy import select

from main_service.models.job_models import Job, JobEvent
from main_service.repositories.event_repository import EventRepository
from main_service.repositories.jobs_repository import JobsRepository
from main_service.schemas.enums import JobEventType, JobStatus
from sqlalchemy.exc import IntegrityError


def _job(user, payload: str = "hello") -> Job:
    return Job(
        user_id=user.id,
        type="email",
        status=JobStatus.PENDING,
        correlation_id="test-correlation-id",
        payload=payload,
        result=None,
        error=None,
    )


@pytest.mark.asyncio
async def test_event_repository_add_persists_event(session, user):
    event_repo = EventRepository()
    job_repo = JobsRepository()

    job = _job(user)
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
async def test_event_repository_add_persists_payload(session, user):
    event_repo = EventRepository()
    job_repo = JobsRepository()

    job = _job(user)
    job = await job_repo.add(job, session)

    eve = JobEvent(
        job_id = job.id,
        event_type = JobEventType.CREATED,
        sequence_no = 1,
        payload = {"type" : job.type},
    )
    eve = await event_repo.add(eve, session)

    statement = select(JobEvent).where(JobEvent.id == eve.id)
    res = await session.execute(statement)
    res = res.scalar_one_or_none()

    assert res.payload == {"type" : "email"}


@pytest.mark.asyncio
async def test_event_repository_add_allows_multiple_events_for_same_job_with_different_sequence(session, user):
    event_repo = EventRepository()
    job_repo = JobsRepository()

    job = _job(user)
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

    assert seques == [eve_1.sequence_no, eve_2.sequence_no]


@pytest.mark.asyncio
async def test_event_repository_add_raises_integrity_error_for_duplicate_sequence_no_per_job(session, user):
    event_repo = EventRepository()
    job_repo = JobsRepository()

    job = _job(user)
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
        await event_repo.add(eve_2, session)
    await session.rollback()


@pytest.mark.asyncio
async def test_event_repository_add_allows_same_sequence_no_for_different_jobs(session, user):
    event_repo = EventRepository()
    job_repo = JobsRepository()

    job_1 = _job(user)
    job_2 = _job(user)
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

    statement = select(JobEvent).order_by(JobEvent.job_id)
    res = await session.execute(statement)
    res = res.scalars().all()

    seques = [[eve.job_id, eve.sequence_no] for eve in res]

    assert seques == [[eve_1.job_id, eve_1.sequence_no], [eve_2.job_id, eve_2.sequence_no]]


@pytest.mark.asyncio
async def test_event_repository_get_filters_by_job_id_and_applies_skip_and_limit(session, user):
    event_repo = EventRepository()
    job_repo = JobsRepository()

    job = await job_repo.add(
        _job(user),
        session,
    )
    other_job = await job_repo.add(
        _job(user, payload="other"),
        session,
    )

    await event_repo.add(
        JobEvent(
            job_id=job.id,
            event_type=JobEventType.CREATED,
            sequence_no=1,
            payload={"progress": "0%"},
        ),
        session,
    )
    await event_repo.add(
        JobEvent(
            job_id=job.id,
            event_type=JobEventType.RUNNING,
            sequence_no=2,
            payload={"progress": "50%"},
        ),
        session,
    )
    await event_repo.add(
        JobEvent(
            job_id=job.id,
            event_type=JobEventType.FINISHED,
            sequence_no=3,
            payload={"progress": "100%"},
        ),
        session,
    )
    await event_repo.add(
        JobEvent(
            job_id=other_job.id,
            event_type=JobEventType.CREATED,
            sequence_no=1,
            payload={"type": "email"},
        ),
        session,
    )

    result = await event_repo.get(job_id=job.id, session=session, skip=1, limit=2)

    assert [event.sequence_no for event in result] == [2, 3]
    assert all(event.job_id == job.id for event in result)

