from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from main_service.schemas.webhook_schemas import *

from main_service.services.webhook_service import WebhookService
from main_service.api.dependencies import create_webhook_service_instance, get_db_session


router = APIRouter(
    prefix="/webhook",
    tags=["webhooks"]
)


@router.post("", response_model=CreateWebhookResponse)
async def post_webhook(
    webhook_req: CreateWebhookRequest,
    webhook_service: WebhookService = Depends(create_webhook_service_instance),
    session: AsyncSession = Depends(get_db_session)
):
    webhook = await webhook_service.create_webhook(webhook_req, session)
    return webhook


