import asyncio
import hmac
import json
import secrets
from hashlib import sha256

import httpx
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from contracts import webhook_pb2
from contracts.webhook_pb2_grpc import WebhookSenderStub
from main_service.core.exception.exception import (
    JobNotFoundError,
    WebhookCreateError,
    WebhookDeleteError,
    WebhookNotFoundError,
)
from main_service.core.logging.logging import get_logger
from main_service.db.session import AsyncSessionLocal
from main_service.models.webhook_models import WebhookSubscription
from main_service.repositories.jobs_repository import JobsRepository
from main_service.repositories.webhook_repository import WebhookRepository
from main_service.schemas.enums import WebhookDeliveryStatus
from main_service.schemas.webhook_schemas import CreateWebhookRequest
from main_service.core.context.context import context_correlation_id


logger = get_logger(__name__)


class WebhookService:
    def __init__(self, job_repo: JobsRepository, webhook_repo: WebhookRepository, webhook_sender: WebhookSenderStub):
        self.job_repo = job_repo
        self.webhook_repo = webhook_repo
        self.webhook_sender = webhook_sender

    async def create_webhook(self, webhook_req: CreateWebhookRequest, session: AsyncSession) -> WebhookSubscription:
        job_exists = await self.job_repo.job_exist(webhook_req.job_id, session)
        if not job_exists:
            logger.warning(
                "Webhook creation rejected because job was not found",
                extra={
                    "event": "webhook_creation_rejected",
                    "job_id": webhook_req.job_id,
                    "target_url": str(webhook_req.target_url),
                },
            )
            raise JobNotFoundError(webhook_req.job_id)

        try:
            webhook = WebhookSubscription(
                job_id=webhook_req.job_id,
                target_url=str(webhook_req.target_url),
                secret=secrets.token_hex(32),
                is_active=True,
            )
            webhook = await self.webhook_repo.add(webhook, session)
        except Exception:
            await session.rollback()
            logger.exception(
                "Webhook creation failed",
                extra={
                    "event": "webhook_creation_failed",
                    "job_id": webhook_req.job_id,
                    "target_url": str(webhook_req.target_url),
                },
            )
            raise WebhookCreateError(webhook_req.job_id)
        else:
            await session.commit()
            await session.refresh(webhook)

        logger.info(
            "Webhook created",
            extra={
                "event": "webhook_created",
                "webhook_id": webhook.id,
                "job_id": webhook.job_id,
                "target_url": webhook.target_url,
            },
        )

        return webhook

    async def dispatch_job_event(self, job_id: int) -> None:
        async with AsyncSessionLocal() as session:
            job = await self.job_repo.find_job_by_id(job_id, session)
            webhooks = await self.webhook_repo.find_wbhooks_by_job_id(job_id, session)

        if not job:
            logger.warning(
                "Webhook dispatch skipped because job was not found",
                extra={
                    "event": "webhook_dispatch_skipped_missing_job",
                    "job_id": job_id,
                },
            )
            return

        active_webhooks = [webhook for webhook in webhooks if webhook.is_active]
        if not active_webhooks:
            logger.info(
                "Webhook dispatch skipped because no active subscriptions were found",
                extra={
                    "event": "webhook_dispatch_skipped_no_active_webhooks",
                    "job_id": job_id,
                    "webhook_count": len(webhooks),
                },
            )
            return

        logger.info(
            "Webhook dispatch started",
            extra={
                "event": "webhook_dispatch_started",
                "job_id": job.id,
                "job_status": job.status,
                "webhook_count": len(active_webhooks),
            },
        )

        req_payload = webhook_pb2.WebhookPayload(
            job_id=job.id,
            job_status=job.status,
            finished_at=job.finished_at,
        )

        tasks = [
            self.webhook_sender.SendWebhook(
                webhook_pb2.SendWebhookRequest(
                    webhook_id=webhook.id,
                    target_url=webhook.target_url,
                    payload=req_payload,
                    secret=webhook.secret,
                ),
                timeout=60,
                metadata=(
                    ("x-correlation-id", context_correlation_id.get()),
                )
            )
            for webhook in active_webhooks
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        sent_count = 0
        failed_count = 0

        async with AsyncSessionLocal() as session:
            try:
                for webhook, res in zip(active_webhooks, results):
                    if isinstance(res, Exception):
                        failed_count += 1
                        logger.exception(
                            "Webhook dispatch call failed",
                            extra={
                                "event": "webhook_dispatch_call_failed",
                                "job_id": job.id,
                                "job_status": job.status,
                                "webhook_id": webhook.id,
                                "target_url": webhook.target_url,
                            },
                            exc_info=(type(res), res, res.__traceback__),
                        )
                        continue

                    if res.status == "failed":
                        failed_count += 1
                        logger.warning(
                            "Webhook dispatch completed with failure",
                            extra={
                                "event": "webhook_dispatch_result",
                                "job_id": job.id,
                                "job_status": job.status,
                                "webhook_id": res.webhook_id,
                                "target_url": webhook.target_url,
                                "delivery_status": res.status,
                                "error_message": res.error or None,
                            },
                        )
                        await self.webhook_repo.update_result_fields(
                            error=res.error,
                            id=res.webhook_id,
                            session=session,
                            status=WebhookDeliveryStatus.FAILED,
                        )
                    elif res.status == "sent":
                        sent_count += 1
                        logger.info(
                            "Webhook dispatch completed successfully",
                            extra={
                                "event": "webhook_dispatch_result",
                                "job_id": job.id,
                                "job_status": job.status,
                                "webhook_id": res.webhook_id,
                                "target_url": webhook.target_url,
                                "delivery_status": res.status,
                            },
                        )
                        await self.webhook_repo.update_result_fields(
                            error=None,
                            id=res.webhook_id,
                            session=session,
                            status=WebhookDeliveryStatus.SENT,
                        )
            except Exception:
                await session.rollback()
                logger.exception(
                    "Webhook delivery status persistence failed",
                    extra={
                        "event": "webhook_delivery_status_persist_failed",
                        "job_id": job.id,
                    },
                )
                return

            await session.commit()

        logger.info(
            "Webhook dispatch completed",
            extra={
                "event": "webhook_dispatch_completed",
                "job_id": job.id,
                "job_status": job.status,
                "webhook_count": len(active_webhooks),
                "sent_count": sent_count,
                "failed_count": failed_count,
            },
        )

    async def deliver(self, webhook: WebhookSubscription, client: httpx.AsyncClient, payload: dict):
        safe_payload = jsonable_encoder(payload)
        body = json.dumps(safe_payload, separators=(",", ":")).encode()

        sign = hmac.new(
            key=webhook.secret.encode(),
            msg=body,
            digestmod=sha256,
        ).hexdigest()

        delays = [0, 1, 2, 4]
        last_error = None
        status_code = None
        success = False
        job_id = safe_payload.get("job_id")
        attempt_count = 0

        logger.info(
            "Webhook delivery started",
            extra={
                "event": "webhook_delivery_started",
                "webhook_id": webhook.id,
                "job_id": job_id,
                "target_url": webhook.target_url,
            },
        )

        for attempt, delay in enumerate(delays, start=1):
            attempt_count = attempt
            if delay:
                await asyncio.sleep(delay)

            try:
                resp = await client.post(
                    url=webhook.target_url,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Webhook-Signature": sign,
                    },
                    timeout=5.0,
                )

                if 200 <= resp.status_code < 300:
                    status_code = resp.status_code
                    success = True
                    logger.info(
                        "Webhook delivery succeeded",
                        extra={
                            "event": "webhook_delivery_succeeded",
                            "webhook_id": webhook.id,
                            "job_id": job_id,
                            "target_url": webhook.target_url,
                            "status_code": status_code,
                            "attempt": attempt,
                        },
                    )
                    break

                if 500 <= resp.status_code < 600:
                    status_code = resp.status_code
                    last_error = f"server error: {resp.status_code}"
                    logger.warning(
                        "Webhook delivery retryable failure",
                        extra={
                            "event": "webhook_delivery_retryable_failure",
                            "webhook_id": webhook.id,
                            "job_id": job_id,
                            "target_url": webhook.target_url,
                            "status_code": status_code,
                            "attempt": attempt,
                            "retry_in_s": delays[attempt] if attempt < len(delays) else None,
                            "error_message": last_error,
                        },
                    )
                    continue

                if 400 <= resp.status_code < 500:
                    status_code = resp.status_code
                    last_error = f"client error {resp.status_code}"
                    logger.warning(
                        "Webhook delivery failed",
                        extra={
                            "event": "webhook_delivery_failed",
                            "webhook_id": webhook.id,
                            "job_id": job_id,
                            "target_url": webhook.target_url,
                            "status_code": status_code,
                            "attempt": attempt,
                            "error_message": last_error,
                        },
                    )
                    break

            except httpx.TimeoutException as ex:
                last_error = "timeout"
                logger.warning(
                    "Webhook delivery retryable failure",
                    extra={
                        "event": "webhook_delivery_retryable_failure",
                        "webhook_id": webhook.id,
                        "job_id": job_id,
                        "target_url": webhook.target_url,
                        "attempt": attempt,
                        "retry_in_s": delays[attempt] if attempt < len(delays) else None,
                        "error_type": type(ex).__name__,
                        "error_message": last_error,
                    },
                )
                continue
            except httpx.RequestError as ex:
                last_error = f"Request error: {str(ex)}"
                logger.warning(
                    "Webhook delivery retryable failure",
                    extra={
                        "event": "webhook_delivery_retryable_failure",
                        "webhook_id": webhook.id,
                        "job_id": job_id,
                        "target_url": webhook.target_url,
                        "attempt": attempt,
                        "retry_in_s": delays[attempt] if attempt < len(delays) else None,
                        "error_type": type(ex).__name__,
                        "error_message": last_error,
                    },
                )
                continue

        if not success:
            logger.warning(
                "Webhook delivery finished with failure",
                extra={
                    "event": "webhook_delivery_finished_with_failure",
                    "webhook_id": webhook.id,
                    "job_id": job_id,
                    "target_url": webhook.target_url,
                    "status_code": status_code,
                    "attempt": attempt_count,
                    "error_message": last_error,
                },
            )

        return {
            "id": webhook.id,
            "success": success,
            "status_code": status_code,
            "error": last_error,
        }

    async def delete_by_id(self, webhook_id: int, session: AsyncSession) -> dict:
        if not await self.webhook_repo.webhook_exist(webhook_id, session):
            logger.warning(
                "Webhook not found",
                extra={
                    "event": "webhook_not_found",
                    "webhook_id": webhook_id,
                },
            )
            raise WebhookNotFoundError(webhook_id)

        try:
            await self.webhook_repo.delete(webhook_id, session)
            await session.commit()
            logger.info(
                "Webhook deleted",
                extra={
                    "event": "webhook_deleted",
                    "webhook_id": webhook_id,
                },
            )
            return {
                "id": webhook_id,
                "result": "Webhook deleted",
            }
        except Exception:
            await session.rollback()
            logger.exception(
                "Webhook deletion failed",
                extra={
                    "event": "webhook_delete_failed",
                    "webhook_id": webhook_id,
                },
            )
            raise WebhookDeleteError(webhook_id)
