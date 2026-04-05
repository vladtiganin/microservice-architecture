from main_service.repositories.event_repository import EventRepository
from main_service.repositories.jobs_repository import JobsRepository
from main_service.db.session import AsyncSessionLocal
from main_service.services.transition import transition_job
from main_service.schemas.enums import JobEventType, JobStatus

import asyncio

class JobExecutor:
    def __init__(self, job_repo: JobsRepository, event_repo: EventRepository):
        self.job_repo = job_repo
        self.event_repo = event_repo

    async def run_job(self, job_id: int):
        async with AsyncSessionLocal() as session:
            job = await self.job_repo.find_job_by_id(job_id, session)
            if job is None:
                return
            
        await transition_job(
            job_id=job.id,
            job_status=JobStatus.RUNNING,
            event_type=JobEventType.STARTED,
            job_repo=self.job_repo,
            event_repo=self.event_repo,
            event_payload={"progress": "0%"},
            job_payload=job.payload
        )  

        try:
            await asyncio.sleep(1)
            await transition_job(
            job_id=job.id,
            job_status=JobStatus.RUNNING,
            event_type=JobEventType.RUNNING,
            job_repo=self.job_repo,
            event_repo=self.event_repo,
            event_payload={"progress": "20%"},
            job_payload=job.payload
        )  
            await asyncio.sleep(2)
            await transition_job(
            job_id=job.id,
            job_status=JobStatus.RUNNING,
            event_type=JobEventType.RUNNING,
            job_repo=self.job_repo,
            event_repo=self.event_repo,
            event_payload={"progress": "70%"},
            job_payload=job.payload
        )  
            await asyncio.sleep(1)
            await transition_job(
            job_id=job.id,
            job_status=JobStatus.SUCCEEDED,
            event_type=JobEventType.FINISHED,
            job_repo=self.job_repo,
            event_repo=self.event_repo,
            event_payload={"progress": "100%"},
            job_payload=job.payload,
            result=job.payload
        )  
        except Exception as ex:
            await transition_job(
            job_id=job.id,
            job_status=JobStatus.FAILED,
            event_type=JobEventType.FAILED,
            job_repo=self.job_repo,
            event_repo=self.event_repo,
            event_payload={"error" : "Somthig goes wrong during executing program."},
            job_payload=job.payload,
            error=type(ex).__name__
        )  


