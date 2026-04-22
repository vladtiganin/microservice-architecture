from unittest.mock import Mock

import pytest

from main_service.api import dependencies
from main_service.repositories.event_repository import EventRepository
from main_service.repositories.jobs_repository import JobsRepository
from main_service.repositories.webhook_repository import WebhookRepository
from main_service.services.job_service import JobService
from main_service.services.webhook_service import WebhookService


class SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_pagination_parameters_returns_skip_and_limit():
    assert dependencies.pagination_parameters(skip=5, limit=20) == {
        "skip": 5,
        "limit": 20,
    }


def test_dependency_helpers_return_singletons():
    assert dependencies.create_event_repository_instance() is dependencies.event_repo
    assert dependencies.create_job_repository_instance() is dependencies.job_repo
    assert dependencies.create_webhook_repository_instance() is dependencies.webhook_repo
    assert dependencies.create_job_executor_instance() is dependencies.executor_stab
    assert dependencies.create_webhook_service_instance() is dependencies.webhook_service


def test_create_job_service_instance_builds_service_from_dependencies():
    job_repo = Mock(spec=JobsRepository)
    event_repo = Mock(spec=EventRepository)
    job_executor = Mock()

    service = dependencies.create_job_service_instance(
        job_repo=job_repo,
        event_repo=event_repo,
        job_executor=job_executor,
    )

    assert isinstance(service, JobService)
    assert service.job_repo is job_repo
    assert service.event_repo is event_repo
    assert service.job_executor is job_executor


@pytest.mark.asyncio
async def test_get_db_session_yields_session_from_async_session_local(monkeypatch):
    session = Mock()
    monkeypatch.setattr(
        dependencies,
        "AsyncSessionLocal",
        lambda: SessionContext(session),
    )

    generator = dependencies.get_db_session()
    yielded_session = await anext(generator)

    assert yielded_session is session

    with pytest.raises(StopAsyncIteration):
        await anext(generator)


def test_create_webhook_service_instance_returns_webhook_service_singleton():
    assert isinstance(dependencies.create_webhook_service_instance(), WebhookService)
