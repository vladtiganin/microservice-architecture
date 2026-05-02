from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from main_service.api import dependencies
from main_service.core.security.dependencies import get_curr_user
from main_service.models.user_models import User
from main_service.schemas.jobs_schemas import CreateJobRequest, JobListResponse, JobResponse, CreateJobResponse, JobStatusResponse, JobEventsListResponse
from main_service.services import job_service


router = APIRouter(
    prefix="/jobs",
    tags=["jobs"]
)


@router.get("", response_model=JobListResponse)
async def get_jobs(
    request: dict = Depends(dependencies.pagination_parameters),
    service: job_service.JobService = Depends(dependencies.create_job_service_instance),
    session: AsyncSession = Depends(dependencies.get_db_session)
    ):
    return await service.get_jobs(
        skip=request["skip"], 
        limit=request["limit"],
        session=session
    )


@router.post("", response_model=CreateJobResponse)
async def post_job(
    job: CreateJobRequest,
    current_user: User = Depends(get_curr_user),
    service: job_service.JobService = Depends(dependencies.create_job_service_instance),
    session: AsyncSession = Depends(dependencies.get_db_session)
    ):
    res =  await service.create_job(job=job, user_id=current_user.id, session=session)

    resp = {
        "id": res.id,
        "message": "To track job GET it by id"
    }

    return resp


@router.get("/{job_id}", response_model=JobResponse)
async def get_job_by_id(
    job_id: int,
    service: job_service.JobService = Depends(dependencies.create_job_service_instance),
    session: AsyncSession = Depends(dependencies.get_db_session)
    ):
    return await service.get_job_by_id(
        job_id=job_id, 
        session=session
    )


@router.get("/{job_id}/status", response_model=JobStatusResponse)
async def get_job_curr_status(
    job_id: int,
    service: job_service.JobService = Depends(dependencies.create_job_service_instance),
    session: AsyncSession = Depends(dependencies.get_db_session)  
):
    job = await service.get_job_by_id(job_id, session)
    return {
        "id": job.id,
        "status": job.status,
        "updated_at": job.updated_at 
    }


@router.get("/{job_id}/events", response_model=JobEventsListResponse)
async def get_job_events(
    job_id: int,
    request: dict = Depends(dependencies.pagination_parameters),
    service: job_service.JobService = Depends(dependencies.create_job_service_instance),
    session: AsyncSession = Depends(dependencies.get_db_session)    
):
    return await service.get_job_events_by_id(
        job_id=job_id,
        skip=request["skip"],
        limit=request["limit"],
        session=session
    )


@router.get("/{job_id}/events/stream") 
async def get_job_events_stream(
    job_id: int,
    request: Request,
    service: job_service.JobService = Depends(dependencies.create_job_service_instance),
) -> StreamingResponse:
    last_sse_event_header = request.headers.get("last-event-id")
    last_sse_event_id = int(last_sse_event_header) if last_sse_event_header is not None else 0
    return StreamingResponse(
        service.generate_sse_job_event_stream(job_id, request, last_sse_event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control" : "no-cache",
            "Connection": "keep-alive"
        }
    )
