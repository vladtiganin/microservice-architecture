import pytest

from main_service.models.job_models import Job
from main_service.repositories.jobs_repository import JobsRepository
from main_service.schemas.enums import JobStatus


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
async def test_jobs_repository_add_persists_job(session, user):
    repo = JobsRepository()

    job = _job(user)

    saved_job = await repo.add(job, session)

    assert saved_job.id is not None
    assert saved_job.user_id == user.id
    assert saved_job.type == "email"
    assert saved_job.payload == "hello"
    assert saved_job.status == JobStatus.PENDING


@pytest.mark.asyncio
async def test_jobs_repository_get_returns_jobs_ordered_by_id(session, user):
    repo = JobsRepository()

    job_1 = _job(user)
    job_2 = _job(user)
    job_3 = _job(user)

    await repo.add(job_1, session)
    await repo.add(job_2, session)
    await repo.add(job_3, session)

    res = await repo.get(session)

    ids = [job.id for job in res]

    assert ids == [job_1.id, job_2.id, job_3.id]


@pytest.mark.asyncio
async def test_jobs_repository_get_applies_skip_and_limit(session, user):
    repo = JobsRepository()

    job_1 = _job(user)
    job_2 = _job(user)
    job_3 = _job(user)
    job_4 = _job(user)
    job_5 = _job(user)

    await repo.add(job_1, session)
    await repo.add(job_2, session)
    await repo.add(job_3, session)
    await repo.add(job_4, session)
    await repo.add(job_5, session)

    res = await repo.get(session, skip=1, limit=2)

    ids = [job.id for job in res]

    assert ids == [job_2.id, job_3.id]


@pytest.mark.asyncio
async def test_jobs_repository_find_job_by_id_returns_job_when_exists(session, user):
    repo = JobsRepository()

    job = _job(user)

    await repo.add(job, session)

    res = await repo.find_job_by_id(job.id, session)

    assert res.id == job.id


@pytest.mark.asyncio
async def test_jobs_repository_find_job_by_id_returns_none_when_not_exists(session):
    repo = JobsRepository()

    res = await repo.find_job_by_id(99999, session)

    assert res is None


@pytest.mark.asyncio
async def test_jobs_repository_job_exist_returns_boolean(session, user):
    repo = JobsRepository()
    job = _job(user)

    saved_job = await repo.add(job, session)

    assert await repo.job_exist(saved_job.id, session) is True
    assert await repo.job_exist(99999, session) is False













