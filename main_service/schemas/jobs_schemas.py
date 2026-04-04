from pydantic import BaseModel, ConfigDict
from main_service.schemas.enums import JobStatus
from datetime import datetime


class GetJobsRequest(BaseModel):
    skip: int = 0
    limit: int = 10


class CreateJobRequest(BaseModel):
    type: str
    payload: str


class CreateJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int 
    message: str


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    status: JobStatus
    payload: str
    result: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None 


class JobListResponse(BaseModel):
    items: list[JobResponse]