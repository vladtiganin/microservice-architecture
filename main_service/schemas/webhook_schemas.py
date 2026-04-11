from datetime import datetime
from pydantic import BaseModel, ConfigDict, HttpUrl


class CreateWebhookRequest(BaseModel):
    job_id: int
    target_url: HttpUrl
    

class CreateWebhookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    target_url: HttpUrl
    secret: str
    created_at: datetime


