import asyncio
import json
from asyncio import create_task
from datetime import datetime

import grpc
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from contracts import executor_pb2
from contracts.executor_pb2_grpc import ExecutorStub
from main_service.core.exception.exception import JobCreateError, JobNotFoundError
from main_service.core.logging.logging import get_logger
from main_service.db.session import AsyncSessionLocal
from main_service.models.job_models import Job, JobEvent
from main_service.repositories.event_repository import EventRepository
from main_service.repositories.jobs_repository import JobsRepository
from main_service.schemas.enums import JobEventType, JobStatus
from main_service.schemas.jobs_schemas import CreateJobRequest, JobListResponse
from main_service.services.transition import transition_job
from main_service.core.context.context import context_correlation_id


logger = get_logger(__name__)


class JobService:
    def __init__(self, job_repo: JobsRepository, event_repo: EventRepository, job_executor: ExecutorStub):
        self.job_repo = job_repo
        self.event_repo = event_repo
        self.job_executor = job_executor

    async def get_jobs(self, session: AsyncSession, skip: int = 0, limit: int = 10) -> JobListResponse:
        logger.info(
            "Jobs list requested",
            extra={
                "event": "jobs_list_requested",
                "skip": skip,
                "limit": limit,
            },
        )
        return {"items": await self.job_repo.get(session, skip, limit)}

    async def create_job(self, job: CreateJobRequest, user_id: int, session: AsyncSession) -> Job:
        logger.info(
            "Job creation requested",
            extra={
                "event": "job_creation_requested",
                "job_type": job.type,
                "user_id": user_id,
            },
        )

        new_job = Job(
            user_id=user_id,
            type=job.type,
            payload=job.payload,
            status=JobStatus.PENDING,
            correlation_id=context_correlation_id.get(),
        )

        try:
            new_job = await self.job_repo.add(new_job, session)

            event = JobEvent(
                job_id=new_job.id,
                event_type=JobEventType.CREATED,
                sequence_no=1,
                payload={
                    "type": new_job.type,
                },
            )
            await self.event_repo.add(event, session)
        except Exception:
            await session.rollback()
            logger.exception(
                "Job creation failed",
                extra={
                    "event": "job_creation_failed",
                    "job_type": job.type,
                },
            )
            raise JobCreateError(job.type)
        else:
            await session.commit()
            await session.refresh(new_job)

        logger.info(
            "Job created",
            extra={
                "event": "job_created",
                "job_id": new_job.id,
                "user_id": new_job.user_id,
                "job_type": new_job.type,
                "job_status": new_job.status,
            },
        )

        await transition_job(
            job_id=new_job.id,
            job_status=JobStatus.QUEUED,
            event_type=JobEventType.QUEUED,
            event_payload={"time": datetime.now().isoformat()},
            job_repo=self.job_repo,
            event_repo=self.event_repo,
        )

        create_task(self._manage_job_executing(new_job))

        return new_job

    async def _manage_job_executing(self, job: Job) -> None:
        req = executor_pb2.ExecuteJobRequest(
            job_id=job.id,
            type=job.type,
            payload=job.payload,

        )

        logger.info(
            "Executor job execution started",
            extra={
                "event": "executor_job_execution_started",
                "job_id": job.id,
                "job_type": job.type,
                "grpc_method": "ExecuteJob",
            },
        )

        try:
            resp_stream = self.job_executor.ExecuteJob(
                req, 
                timeout=60,
                metadata=(
                    ("x-correlation-id", context_correlation_id.get()),
                )
            )
            last_status = None
            last_error = None

            async for resp in resp_stream:
                event_type, job_status = JobService._define_status_type(resp.status)
                last_status = resp.status
                last_error = resp.error or None

                await transition_job(
                    job_id=job.id,
                    job_status=job_status,
                    event_type=event_type,
                    job_repo=self.job_repo,
                    event_repo=self.event_repo,
                    event_payload={"progress": f"{resp.progress}%"},
                    result=resp.result if resp.result else None,
                    error=resp.error if resp.error else None,
                )

            logger_method = logger.warning if last_status == "failed" else logger.info
            logger_method(
                "Executor job execution completed",
                extra={
                    "event": "executor_job_execution_completed",
                    "job_id": job.id,
                    "job_type": job.type,
                    "job_status": last_status or "unknown",
                    "grpc_method": "ExecuteJob",
                    "error_message": last_error,
                },
            )
        except grpc.aio.AioRpcError as ex:
            logger.error(
                "Executor job execution failed",
                extra={
                    "event": "executor_job_execution_failed",
                    "job_id": job.id,
                    "job_type": job.type,
                    "grpc_method": "ExecuteJob",
                    "error_type": ex.code().name,
                    "error_message": ex.details() or ex.code().name,
                },
            )
            await transition_job(
                job_id=job.id,
                job_status=JobStatus.FAILED,
                event_type=JobEventType.FAILED,
                job_repo=self.job_repo,
                event_repo=self.event_repo,
                event_payload={"grpc_error": ex.code().name},
                error=ex.details() or ex.code().name,
            )
        except Exception as ex:
            logger.exception(
                "Executor job execution failed unexpectedly",
                extra={
                    "event": "executor_job_execution_failed",
                    "job_id": job.id,
                    "job_type": job.type,
                    "grpc_method": "ExecuteJob",
                },
            )
            await transition_job(
                job_id=job.id,
                job_status=JobStatus.FAILED,
                event_type=JobEventType.FAILED,
                job_repo=self.job_repo,
                event_repo=self.event_repo,
                event_payload={"error_type": type(ex).__name__},
                error=str(ex),
            )

    @staticmethod
    def _define_status_type(status: str) -> tuple[JobEventType, JobStatus]:
        match status:
            case "running":
                return (JobEventType.RUNNING, JobStatus.RUNNING)
            case "finished":
                return (JobEventType.FINISHED, JobStatus.SUCCEEDED)
            case "failed":
                return (JobEventType.FAILED, JobStatus.FAILED)
            case _:
                raise ValueError("Unknown status received")

    async def get_job_by_id(self, job_id: int, session: AsyncSession) -> Job:
        job = await self.job_repo.find_job_by_id(job_id, session)

        if job is None:
            logger.warning(
                "Job not found",
                extra={
                    "event": "job_not_found",
                    "job_id": job_id,
                },
            )
            raise JobNotFoundError(job_id)

        return job

    async def get_job_events_by_id(
        self,
        job_id: int,
        session: AsyncSession,
        skip: int = 0,
        limit: int = 25,
    ) -> dict[str, list[JobEvent]]:
        logger.info(
            "Job events requested",
            extra={
                "event": "job_events_requested",
                "job_id": job_id,
                "skip": skip,
                "limit": limit,
            },
        )
        return {"items": await self.event_repo.get(job_id, session, skip, limit)}

    async def generate_sse_job_event_stream(
        self,
        job_id: int,
        request: Request,
        last_sse_event_id: int | None = None,
    ):
        async with AsyncSessionLocal() as session:
            res = await self.job_repo.job_exist(job_id, session)
            if not res:
                logger.warning(
                    "SSE stream rejected because job was not found",
                    extra={
                        "event": "job_events_stream_rejected",
                        "job_id": job_id,
                    },
                )
                raise JobNotFoundError(job_id)

        sse_event_id = last_sse_event_id if last_sse_event_id is not None else 0
        close_reason = "completed"

        logger.info(
            "SSE stream opened",
            extra={
                "event": "job_events_stream_opened",
                "job_id": job_id,
                "last_event_id": sse_event_id,
            },
        )

        try:
            while True:
                if await request.is_disconnected():
                    close_reason = "client_disconnected"
                    break

                async with AsyncSessionLocal() as session:
                    event = await self.event_repo.get(
                        job_id=job_id,
                        session=session,
                        skip=sse_event_id,
                        limit=1,
                    )
                    if not event:
                        yield ": ping\n\n"
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
                    resp = (
                        f"id: {event.sequence_no}\n"
                        f"event: {event.event_type}\n"
                        f"data: {json.dumps(event_data)}\n\n"
                    )
                    yield resp

                    sse_event_id = event.sequence_no
                    if event.event_type in {JobEventType.FINISHED, JobEventType.FAILED}:
                        close_reason = "terminal_event_sent"
                        logger.info(
                            "SSE terminal event sent",
                            extra={
                                "event": "job_events_stream_terminal_event_sent",
                                "job_id": job_id,
                                "event_type": event.event_type,
                                "sequence_no": event.sequence_no,
                            },
                        )
                        break
        except Exception:
            close_reason = "error"
            logger.exception(
                "SSE stream failed",
                extra={
                    "event": "job_events_stream_failed",
                    "job_id": job_id,
                },
            )
            raise
        finally:
            logger.info(
                "SSE stream closed",
                extra={
                    "event": "job_events_stream_closed",
                    "job_id": job_id,
                    "last_event_id": sse_event_id,
                    "close_reason": close_reason,
                },
            )
