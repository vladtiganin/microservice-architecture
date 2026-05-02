import pytest
from sqlalchemy import select

from main_service.models.job_models import Job
from main_service.models.webhook_models import WebhookSubscription
from main_service.repositories.jobs_repository import JobsRepository
from main_service.repositories.webhook_repository import WebhookRepository
from main_service.schemas.enums import JobStatus, WebhookDeliveryStatus


async def _create_job(session, user):
    job_repo = JobsRepository()
    return await job_repo.add(
        Job(
            user_id=user.id,
            type="email",
            status=JobStatus.PENDING,
            correlation_id="test-correlation-id",
            payload="hello",
            result=None,
            error=None,
        ),
        session,
    )


@pytest.mark.asyncio
async def test_webhook_repository_add_persists_webhook(session, user):
    repo = WebhookRepository()
    job = await _create_job(session, user)

    webhook = WebhookSubscription(
        job_id=job.id,
        target_url="https://example.com/a",
        secret="secret-a",
        is_active=True,
    )

    saved_webhook = await repo.add(webhook, session)

    assert saved_webhook.id is not None
    assert saved_webhook.job_id == job.id
    assert saved_webhook.target_url == "https://example.com/a"
    assert saved_webhook.secret == "secret-a"
    assert saved_webhook.is_active is True


@pytest.mark.asyncio
async def test_webhook_repository_find_wbhooks_by_job_id_returns_ordered_items(session, user):
    repo = WebhookRepository()
    job = await _create_job(session, user)
    other_job = await _create_job(session, user)

    first_webhook = await repo.add(
        WebhookSubscription(
            job_id=job.id,
            target_url="https://example.com/a",
            secret="secret-a",
            is_active=True,
        ),
        session,
    )
    second_webhook = await repo.add(
        WebhookSubscription(
            job_id=job.id,
            target_url="https://example.com/b",
            secret="secret-b",
            is_active=True,
        ),
        session,
    )
    await repo.add(
        WebhookSubscription(
            job_id=other_job.id,
            target_url="https://example.com/c",
            secret="secret-c",
            is_active=True,
        ),
        session,
    )

    result = await repo.find_wbhooks_by_job_id(job.id, session)

    assert [webhook.id for webhook in result] == [first_webhook.id, second_webhook.id]


@pytest.mark.asyncio
async def test_webhook_repository_update_result_fields_updates_status_error_and_active_flag(session, user):
    repo = WebhookRepository()
    job = await _create_job(session, user)
    webhook = await repo.add(
        WebhookSubscription(
            job_id=job.id,
            target_url="https://example.com/a",
            secret="secret-a",
            is_active=True,
        ),
        session,
    )

    await repo.update_result_fields(
        session=session,
        status=WebhookDeliveryStatus.FAILED,
        id=webhook.id,
        error="boom",
    )

    failed_webhook = (
        await session.execute(
            select(WebhookSubscription).where(WebhookSubscription.id == webhook.id)
        )
    ).scalar_one()

    assert failed_webhook.delivery_status == WebhookDeliveryStatus.FAILED
    assert failed_webhook.error == "boom"
    assert failed_webhook.is_active is False

    await repo.update_result_fields(
        session=session,
        status=WebhookDeliveryStatus.SENT,
        id=webhook.id,
        error=None,
    )

    sent_webhook = (
        await session.execute(
            select(WebhookSubscription).where(WebhookSubscription.id == webhook.id)
        )
    ).scalar_one()

    assert sent_webhook.delivery_status == WebhookDeliveryStatus.SENT
    assert sent_webhook.error is None
    assert sent_webhook.is_active is True


@pytest.mark.asyncio
async def test_webhook_repository_webhook_exist_returns_boolean(session, user):
    repo = WebhookRepository()
    job = await _create_job(session, user)
    webhook = await repo.add(
        WebhookSubscription(
            job_id=job.id,
            target_url="https://example.com/a",
            secret="secret-a",
            is_active=True,
        ),
        session,
    )

    assert await repo.webhook_exist(webhook.id, session) is True
    assert await repo.webhook_exist(99999, session) is False


@pytest.mark.asyncio
async def test_webhook_repository_delete_removes_webhook(session, user):
    repo = WebhookRepository()
    job = await _create_job(session, user)
    webhook = await repo.add(
        WebhookSubscription(
            job_id=job.id,
            target_url="https://example.com/a",
            secret="secret-a",
            is_active=True,
        ),
        session,
    )

    await repo.delete(webhook.id, session)

    deleted_webhook = (
        await session.execute(
            select(WebhookSubscription).where(WebhookSubscription.id == webhook.id)
        )
    ).scalar_one_or_none()

    assert deleted_webhook is None
