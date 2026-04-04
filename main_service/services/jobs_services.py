from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from asyncio import create_task

from main_service.models.job_models import Job, JobEvent
from main_service.repositories.event_repository import EventRepository
from main_service.repositories.jobs_repository import JobsRepository
from main_service.schemas.enums import JobStatus, JobEventType
from main_service.schemas.jobs_schemas import CreateJobRequest, JobListResponse
from main_service.services.job_executor import JobExecutor
from main_service.services.transition import transition_job


class JobService:
    def __init__(self, job_repo: JobsRepository, event_repo: EventRepository, job_executor: JobExecutor):
        self.job_repo = job_repo
        self.event_repo = event_repo
        self.job_executor = job_executor

    async def get_jobs(self, session: AsyncSession, skip:int = 0, limit: int = 10) -> JobListResponse:
        return {"items" : await self.job_repo.get(session, skip, limit)}
    

    async def create_job(self, job: CreateJobRequest, session: AsyncSession) -> Job:
        new_job = Job(
            type=job.type, 
            payload=job.payload, 
            status=JobStatus.PENDING)
        eve = None
        
        try:
            new_job = await self.job_repo.add(new_job, session)

            eve = JobEvent(
            job_id=new_job.id, 
            event_type=JobEventType.CREATED, 
            sequence_no=1,
            payload={
                "type" : new_job.type
            })
            eve = await self.event_repo.add(eve, session)
        except Exception:
            await session.rollback()
            raise HTTPException(status_code=500, detail="Error during creating a job")
        else:
            await session.commit()
            await session.refresh(new_job)

        Task = create_task(self.job_executor.run_job(new_job.id))

        transition_job(
            job_id=new_job.id,
            job_status=JobStatus.QUEUED,
            event_type=JobEventType.QUEUED,
        )

        return new_job
    

    async def get_job_by_id(self, job_id: int, session: AsyncSession) -> Job:
        job = await self.job_repo.find_job_by_id(job_id, session)

        if job is None: 
            raise HTTPException(status_code=404, detail="Job with this id not found")
            
        return job


