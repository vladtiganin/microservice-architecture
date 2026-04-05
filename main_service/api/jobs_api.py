from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from main_service.api import dependencies
from main_service.schemas.jobs_schemas import CreateJobRequest, JobListResponse, JobResponse, CreateJobResponse
from main_service.services import jobs_services
from asyncio import create_task
from main_service.services.transition import transition_job
from main_service.schemas.enums import JobEventType, JobStatus


router = APIRouter(
    prefix="/jobs",
    tags=["jobs"]
)


@router.get("", response_model=JobListResponse)
async def get_jobs(
    request: dict = Depends(dependencies.pagination_parameters),
    service: jobs_services.JobService = Depends(dependencies.create_job_service_instance),
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
    service: jobs_services.JobService = Depends(dependencies.create_job_service_instance),
    session: AsyncSession = Depends(dependencies.get_db_session)
    ):
    res =  await service.create_job(job=job, session=session)

    resp = {
        "id": res.id,
        "message": "To track job GET it by id"
    }

    return resp


@router.get("/{job_id}", response_model=JobResponse)
async def get_job_by_id(
    job_id: int,
    service: jobs_services.JobService = Depends(dependencies.create_job_service_instance),
    session: AsyncSession =Depends(dependencies.get_db_session)
    ):
    return await service.get_job_by_id(
        job_id=job_id, 
        session=session
    )
