from fastapi import Depends

from main_service.db.session import AsyncSessionLocal
from main_service.repositories.event_repository import EventRepository
from main_service.repositories.jobs_repository import JobsRepository
from main_service.services.job_service import JobService
from main_service.services.job_executor import JobExecutor

async def get_db_session():
    async with AsyncSessionLocal() as session:
        yield session


event_repo = EventRepository()
job_repo = JobsRepository()
job_executor = JobExecutor(job_repo, event_repo)

def pagination_parameters(skip: int = 0, limit: int = 10) -> dict:
    return {
        "skip": skip,
        "limit": limit
    }


def create_event_repository_instance() -> EventRepository:
    return event_repo


def create_job_executor_instance() -> JobExecutor:
    return job_executor


def create_job_repository_instance() -> JobsRepository:
    return job_repo


def create_job_service_instance(
        job_repo: JobsRepository = Depends(create_job_repository_instance),
        event_repo: EventRepository = Depends(create_event_repository_instance),
        job_executor: JobExecutor = Depends(create_job_executor_instance)
        ) -> JobService:
    return JobService(job_repo, event_repo, job_executor)
