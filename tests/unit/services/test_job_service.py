import pytest
from unittest.mock import patch, Mock, AsyncMock

from main_service.services.jobs_services import JobService
from main_service.schemas.jobs_schemas import CreateJobRequest
from main_service.models.job_models import Job
from main_service.schemas.enums import JobStatus, JobEventType
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_get_jobs_returns_items_list():
    job_1, job_2 = Mock(), Mock()

    job_repo = Mock()
    job_repo.get = AsyncMock(return_value=[job_1, job_2])

    event_repo = Mock()
    session = Mock()

    service = JobService(job_repo=job_repo, event_repo=event_repo)
    res = await service.get_jobs(session=session, skip=0, limit=10)

    job_repo.get.assert_awaited_once_with(session, 0, 10)
    assert res == {"items" : [job_1, job_2]}

@pytest.mark.asyncio
async def test_get_jobs_returns_empty_items_when_repository_is_empty():
    job_repo = Mock()
    job_repo.get = AsyncMock(return_value=[])

    event_repo = Mock()
    session = Mock()

    service = JobService(job_repo=job_repo, event_repo=event_repo)
    res = await service.get_jobs(session=session, skip=0, limit=10)

    job_repo.get.assert_awaited_once_with(session, 0, 10)
    assert res == {"items" : []}


@pytest.mark.asyncio
async def test_create_job_creates_job_with_pending_status():
    req = CreateJobRequest(type="email", payload="hello")

    job_repo = Mock()
    job_repo.add = AsyncMock(return_value=Job(id=1))

    event_repo = Mock()
    event_repo.add = AsyncMock()

    session = AsyncMock()
    service = JobService(job_repo, event_repo)
    res = await service.create_job(req, session)

    assert job_repo.add.call_args.args[0].type == "email"
    assert job_repo.add.call_args.args[0].payload == "hello"
    assert job_repo.add.call_args.args[0].status == JobStatus.PENDING


@pytest.mark.asyncio
async def test_create_job_calls_job_repository_add():
    req = CreateJobRequest(type="email", payload="hello")

    job_repo = Mock()
    job_repo.add = AsyncMock(return_value=Job(id=1))

    event_repo = Mock()
    event_repo.add = AsyncMock()

    session = AsyncMock()
    service = JobService(job_repo, event_repo)
    res = await service.create_job(req, session)

    job_repo.add.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_job_creates_created_event_with_sequence_no_1():
    req = CreateJobRequest(type="email", payload="hello")

    job_repo = Mock()
    job_repo.add = AsyncMock(return_value=Job(id=1, type="email"))

    event_repo = Mock()
    event_repo.add = AsyncMock()

    session = AsyncMock()
    service = JobService(job_repo, event_repo)
    res = await service.create_job(req, session)

    assert event_repo.add.call_args.args[0].job_id == 1
    assert event_repo.add.call_args.args[0].event_type == JobEventType.CREATED
    assert event_repo.add.call_args.args[0].sequence_no == 1
    assert event_repo.add.call_args.args[0].payload == {"type" : "email"}


@pytest.mark.asyncio
async def test_create_job_commits_and_refreshes_session_on_success():
    req = CreateJobRequest(type="email", payload="hello")

    job_repo = Mock()
    job_repo.add = AsyncMock(return_value=Job(id=1, type="email"))

    event_repo = Mock()
    event_repo.add = AsyncMock()

    session = AsyncMock()
    service = JobService(job_repo, event_repo)
    res = await service.create_job(req, session)

    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_job_returns_created_job():
    req = CreateJobRequest(type="email", payload="hello")

    job = Job(id = 1, type = "poop", payload = "poop")
    job_repo = Mock()
    job_repo.add = AsyncMock(return_value=job)

    event_repo = Mock()
    event_repo.add = AsyncMock()

    session = AsyncMock()
    service = JobService(job_repo, event_repo)
    res = await service.create_job(req, session)

    assert res == job


@pytest.mark.asyncio
async def test_create_job_rolls_back_and_raises_500_when_job_repo_add_fails():
    req = CreateJobRequest(type="email", payload="hello")

    job_repo = Mock()
    job_repo.add = AsyncMock(side_effect = Exception)

    event_repo = Mock()
    event_repo.add = AsyncMock()

    session = AsyncMock()
    service = JobService(job_repo, event_repo)

    with pytest.raises(HTTPException) as ex:
        res = await service.create_job(req, session)

        ex.value.status_code == 500
        ex.value.detail == "Error during creating a job"
        session.rollback.assert_awaited_once()
        session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_job_rolls_back_and_raises_500_when_event_repo_add_fails():
    req = CreateJobRequest(type="email", payload="hello")

    job = Job(id = 1, type = "poop", payload = "poop")
    job_repo = Mock()
    job_repo.add = AsyncMock(return_value = job)

    event_repo = Mock()
    event_repo.add = AsyncMock(side_effect = Exception)

    session = AsyncMock()
    service = JobService(job_repo, event_repo)

    with pytest.raises(HTTPException) as ex:
        res = await service.create_job(req, session)

        ex.value.status_code == 500
        ex.value.detail == "Error during creating a job"
        session.rollback.assert_awaited_once()
        session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_job_by_id_returns_job_when_found():
    req = CreateJobRequest(type="email", payload="hello")

    fake_job = Mock()

    job_repo = Mock()
    job_repo.find_job_by_id = AsyncMock(return_value = fake_job)

    event_repo = Mock()

    session = AsyncMock()
    service = JobService(job_repo, event_repo)
    
    res = await service.get_job_by_id(1, session)

    assert res == fake_job
    

@pytest.mark.asyncio
async def test_get_job_by_id_raises_404_when_not_found():
    req = CreateJobRequest(type="email", payload="hello")

    job_repo = Mock()
    job_repo.find_job_by_id = AsyncMock(return_value = None)

    event_repo = Mock()

    session = AsyncMock()
    service = JobService(job_repo, event_repo)
    
    with pytest.raises(HTTPException) as ex:
        res = await service.get_job_by_id(1, session)

        ex.value.status_code == 404
        ex.value.detail == "Job with this id not found" 



