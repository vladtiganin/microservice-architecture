from main_service.models.webhook_models import *
from main_service.schemas.enums import WebhookDeliveryStatus
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update


class WebhookRepository:
    def __init__(self):
        pass


    async def add(self, webhook: WebhookSubscription, session: AsyncSession) -> WebhookSubscription:
        session.add(webhook)
        await session.flush()
        return webhook
    

    async def find_wbhooks_by_job_id(self, job_id: int, session: AsyncSession) -> list[WebhookSubscription]:
        statement = select(WebhookSubscription).order_by(WebhookSubscription.id).where(WebhookSubscription.job_id == job_id)
        res = await session.execute(statement)
        return res.scalars().all()
    

    async def update_result_fields(self, session: AsyncSession, status: WebhookDeliveryStatus, id:int, error: str | None = None):
        statement = (
            update(WebhookSubscription)
            .where(WebhookSubscription.id == id)
            .values(
                error=error,
                is_active=(status == WebhookDeliveryStatus.SENT),
                delivery_status=status
                )
            )
        
        await session.execute(statement)


