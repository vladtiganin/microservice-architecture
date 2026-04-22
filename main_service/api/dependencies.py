from fastapi import Depends
import grpc

from main_service.db.session import AsyncSessionLocal
from main_service.repositories.event_repository import EventRepository
from main_service.repositories.jobs_repository import JobsRepository
from main_service.repositories.webhook_repository import WebhookRepository
from main_service.services.job_service import JobService
from main_service.services.webhook_service import WebhookService
from main_service.config import settings
from contracts.executor_pb2_grpc import ExecutorStub 
from contracts.webhook_pb2_grpc import WebhookSenderStub


event_repo = EventRepository()
job_repo = JobsRepository()
webhook_repo = WebhookRepository()

executor_channel = grpc.aio.insecure_channel(f"{settings.executor_service_address}")
executor_stab = ExecutorStub(executor_channel)

webhook_channel = grpc.aio.insecure_channel(f"{settings.webhook_service_address}")
webhook_stab = WebhookSenderStub(webhook_channel)

webhook_service = WebhookService(job_repo, webhook_repo, webhook_stab)


async def get_db_session():
    async with AsyncSessionLocal() as session:
        yield session

def pagination_parameters(skip: int = 0, limit: int = 10) -> dict:
    return {
        "skip": skip,
        "limit": limit
    }


def create_webhook_service_instance() -> WebhookService:
    return webhook_service


def create_event_repository_instance() -> EventRepository:
    return event_repo


def create_webhook_repository_instance() -> WebhookRepository:
    return webhook_repo


def create_job_executor_instance() -> ExecutorStub:
    return executor_stab


def create_job_repository_instance() -> JobsRepository:
    return job_repo


def create_job_service_instance(
        job_repo: JobsRepository = Depends(create_job_repository_instance),
        event_repo: EventRepository = Depends(create_event_repository_instance),
        job_executor: ExecutorStub = Depends(create_job_executor_instance),
        ) -> JobService:
    return JobService(job_repo, event_repo, job_executor)
