from repositories.jobs_repository import JobsRepository
from services.jobs_services import JobService
from fastapi import Depends


repo = JobsRepository()


def pagination_parameters(skip: int = 0, limit: int = 10) -> dict:
    return {
        "skip": skip,
        "limit": limit
    }


def create_repository_instance() -> JobsRepository:
    return repo


def create_job_service_instance(repo: JobsRepository = Depends(create_repository_instance)) -> JobService:
    return JobService(repo)