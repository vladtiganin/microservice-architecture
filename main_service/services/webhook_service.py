from main_service.schemas.webhook_schemas import CreateWebhookRequest
from main_service.models.webhook_models import WebhookSubscription
from main_service.repositories.jobs_repository import JobsRepository
from main_service.repositories.webhook_repository import WebhookRepository
from main_service.db.session import AsyncSessionLocal
from main_service.schemas.enums import WebhookDeliveryStatus

import asyncio
import secrets
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json


class WebhookService:
    def __init__(self, job_repo: JobsRepository, webhook_repo: WebhookRepository):
        self.job_repo = job_repo
        self.webhook_repo = webhook_repo


    async def create_webhook(self, webhook_req: CreateWebhookRequest, session: AsyncSession) -> WebhookSubscription:
        job_exists = await self.job_repo.job_exist(webhook_req.job_id, session)
        if not job_exists:
            raise HTTPException(404, "Job with this id not found")
        
        try:
            webhook= WebhookSubscription(
                job_id=webhook_req.job_id,
                target_url=str(webhook_req.target_url),
                secret=secrets.token_hex(32),
                is_active=True
            )
            webhook = await self.webhook_repo.add(webhook, session)
        except Exception:
            await session.rollback()
            raise HTTPException(500, "Server error, try later")
        else:
            await session.commit()
            await session.refresh(webhook)
        
        return webhook
    

    async def dispatch_job_event(self, job_id: int) -> None:
        async with AsyncSessionLocal() as session:
            job = await self.job_repo.find_job_by_id(job_id, session)
            webhooks = await self.webhook_repo.find_wbhooks_by_job_id(job_id, session)

        if not job or not webhooks:
            return
        
        payload = {
            "job_id": job.id,
            "status": job.status,
            "finished_at": job.finished_at,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        
        async with httpx.AsyncClient() as client:
            tasks = [self.deliver(webhook, client, payload) for webhook in webhooks if webhook.is_active]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        async with AsyncSessionLocal() as session:
            try:
                for res in results:
                    if isinstance(res, Exception):
                        continue #We can process it or log it later.

                    if not res["success"]:
                        await self.webhook_repo.update_result_fields(
                            error=res["error"], 
                            id=res["id"], 
                            session=session,
                            status=WebhookDeliveryStatus.FAILED
                        )
                    elif res["success"]:
                        await self.webhook_repo.update_result_fields(
                            error=None, 
                            id=res["id"], 
                            session=session,
                            status=WebhookDeliveryStatus.SENT
                        )
            except Exception:
                await session.rollback()
            await session.commit()


    async def deliver(self, webhook: WebhookSubscription, client: httpx.AsyncClient, payload: dict):
        safe_payload = jsonable_encoder(payload)
        body = json.dumps(safe_payload, separators=(",", ":")).encode()

        sign = hmac.new(
            key=webhook.secret.encode(),
            msg=body,
            digestmod=sha256
        ).hexdigest()

        delays = [0, 1, 2, 4]
        last_error = None
        status_code = None
        success = False
        for delay in delays:
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
                    success =  True
                    break
                
                if 500 <= resp.status_code < 600:
                    status_code = resp.status_code
                    last_error = f"server error: {resp.status_code}"
                    continue

                if 400 <= resp.status_code < 500:
                    status_code = resp.status_code
                    last_error = f"client error {resp.status_code}: {resp.text}"
                    break


            except httpx.TimeoutException as ex:
                last_error = "timeout"
                continue
            except httpx.RequestError as ex:
                last_error = f"Request error: {str(ex)}"
                continue

        return {
            "id": webhook.id,
            "success": success,
            "status_code": status_code,
            "error": last_error
        }
