from fastapi import APIRouter, Depends
from api import dependencies
from services import jobs_services
from schemas.jobs_schemas import CreateJobRequest, JobListResponse, JobResponse


router = APIRouter(
    prefix="/jobs",
    tags=["jobs"]
)


@router.get("", response_model=JobListResponse)
def get_jobs(
    request: dict = Depends(dependencies.pagination_parameters),
    service: jobs_services.JobService = Depends(dependencies.create_job_service_instance),
    ):
    return service.get_jobs(
        request["skip"], 
        request["limit"]
    )


@router.post("", response_model=JobResponse)
def post_job(
    job: CreateJobRequest,
    service: jobs_services.JobService = Depends(dependencies.create_job_service_instance),
    ):
    return service.create_job(job)


@router.get("/{job_id}", response_model=JobResponse)
def get_job_by_id(
    job_id: int,
    service: jobs_services.JobService = Depends(dependencies.create_job_service_instance),
    ):
    return service.get_job_by_id(job_id)