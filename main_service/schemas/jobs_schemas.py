from pydantic import BaseModel


class GetJobsRequest(BaseModel):
    skip: int = 0
    limit: int = 10


class CreateJobRequest(BaseModel):
    title: str
    description: str | None = None
    is_done: bool = False 


class JobResponse(BaseModel):
    id: int
    title: str
    description: str | None = None
    is_done: bool = False 


class JobListResponse(BaseModel):
    items: list[JobResponse]