from main_service.schemas.jobs_schemas import CreateJobRequest, JobListResponse
from main_service.repositories.event_repository import EventRepository
from main_service.repositories.jobs_repository import JobsRepository
from main_service.schemas.enums import JobStatus, JobEventType
from main_service.services.transition import transition_job
from main_service.services.job_executor import JobExecutor
from main_service.models.job_models import Job, JobEvent
from main_service.db.session import AsyncSessionLocal

from contracts.executor_pb2_grpc import ExecutorStub
from contracts import executor_pb2

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, Request
from asyncio import create_task
from datetime import datetime
import asyncio
import json


class JobService:
    def __init__(self, job_repo: JobsRepository, event_repo: EventRepository, job_executor: ExecutorStub):
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

        await transition_job(
            job_id=new_job.id,
            job_status=JobStatus.QUEUED,
            event_type=JobEventType.QUEUED,
            event_payload={"time" : datetime.now().isoformat()},
            job_repo=self.job_repo,
            event_repo=self.event_repo,
        )

        create_task(self._manage_job_executing(new_job))

        return new_job
    

    async def _manage_job_executing(self, job: Job) -> None:
        req = executor_pb2.ExecuteJobRequest(
            job_id=job.id,
            type=job.type,
            payload=job.payload
        )

        resp_stream = self.job_executor.ExecuteJob(req)
        async for resp in resp_stream:
            event_type, job_status = JobService._defite_status_type(resp.status)

            await transition_job(
                job_id=job.id,
                job_status=job_status,
                event_type=event_type,
                job_repo=self.job_repo,
                event_repo=self.event_repo,
                event_payload={"progress": f"{resp.progress}%"},
                result=resp.result if resp.result else None,
                error=resp.error if resp.error else None
            )

    
    @staticmethod
    def _defite_status_type(status: str) -> list:
        match status:
            case "running": return (JobEventType.RUNNING, JobStatus.RUNNING)
            case "finished": return (JobEventType.FINISHED, JobStatus.SUCCEEDED)
            case "failed": return (JobEventType.FAILED, JobStatus.FAILED) 
    

    async def get_job_by_id(self, job_id: int, session: AsyncSession) -> Job:
        job = await self.job_repo.find_job_by_id(job_id, session)

        if job is None: 
            raise HTTPException(status_code=404, detail="Job with this id not found")
            
        return job


    async def get_job_events_by_id(self, job_id: int, session: AsyncSession, skip: int = 0, limit: int = 25) -> dict["items":list(JobEvent)]:
        return {"items" : await self.event_repo.get(job_id, session, skip, limit)}
    

    async def generate_sse_job_event_stream(self, job_id: int, request:Request, last_sse_event_id: int | None = None):
        async with AsyncSessionLocal() as session:
            res = await self.job_repo.job_exist(job_id, session)
            if not res:
                raise HTTPException(404, "Job not found")


        sse_evet_id = last_sse_event_id if last_sse_event_id is not None else 0
        while True:
            if await request.is_disconnected():
                break

            async with AsyncSessionLocal() as session:
                event = await self.event_repo.get(
                    job_id=job_id,
                    session=session,
                    skip=sse_evet_id,
                    limit=1
                )
                if not event:
                    yield ': ping\n\n'
                    await asyncio.sleep(0.5)
                    continue

                event = event[0]
                event_data = {
                "id": event.id,
                "job_id": event.job_id,
                "event_type": event.event_type.value,
                "sequence_no": event.sequence_no,
                "payload": event.payload,
                "created_at": event.created_at.isoformat(),
                }
                resp = f'id: {event.sequence_no}\nevent: {event.event_type}\ndata: {json.dumps(event_data)}\n\n'
                yield resp

                if event.event_type in {JobEventType.FINISHED, JobEventType.FAILED}:
                    break

                sse_evet_id = event.sequence_no



     




