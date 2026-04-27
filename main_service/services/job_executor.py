import asyncio

from main_service.core.logging.logging import get_logger
from main_service.db.session import AsyncSessionLocal
from main_service.repositories.event_repository import EventRepository
from main_service.repositories.jobs_repository import JobsRepository
from main_service.schemas.enums import JobEventType, JobStatus
from main_service.services.transition import transition_job
from main_service.services.webhook_service import WebhookService


logger = get_logger(__name__)


class JobExecutor:
    def __init__(self, job_repo: JobsRepository, event_repo: EventRepository, webhook_service: WebhookService):
        self.job_repo = job_repo
        self.event_repo = event_repo
        self.webhook_service = webhook_service

    async def run_job(self, job_id: int) -> None:
        async with AsyncSessionLocal() as session:
            job = await self.job_repo.find_job_by_id(job_id, session)
            if job is None:
                logger.warning(
                    "Legacy job execution skipped because job was not found",
                    extra={
                        "event": "legacy_job_execution_skipped",
                        "job_id": job_id,
                    },
                )
                return

        job_type = getattr(job, "type", None)
        logger.info(
            "Legacy job execution started",
            extra={
                "event": "legacy_job_execution_started",
                "job_id": job.id,
                "job_type": job_type,
            },
        )

        await transition_job(
            job_id=job.id,
            job_status=JobStatus.RUNNING,
            event_type=JobEventType.STARTED,
            job_repo=self.job_repo,
            event_repo=self.event_repo,
            event_payload={"progress": "0%"},
            job_payload=job.payload,
        )

        final_status = JobStatus.SUCCEEDED
        try:
            await asyncio.sleep(1)
            await transition_job(
                job_id=job.id,
                job_status=JobStatus.RUNNING,
                event_type=JobEventType.RUNNING,
                job_repo=self.job_repo,
                event_repo=self.event_repo,
                event_payload={"progress": "20%"},
                job_payload=job.payload,
            )
            await asyncio.sleep(2)
            await transition_job(
                job_id=job.id,
                job_status=JobStatus.RUNNING,
                event_type=JobEventType.RUNNING,
                job_repo=self.job_repo,
                event_repo=self.event_repo,
                event_payload={"progress": "70%"},
                job_payload=job.payload,
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
                result=job.payload,
            )
        except Exception as ex:
            final_status = JobStatus.FAILED
            logger.exception(
                "Legacy job execution failed",
                extra={
                    "event": "legacy_job_execution_failed",
                    "job_id": job.id,
                    "job_type": job_type,
                },
            )
            await transition_job(
                job_id=job.id,
                job_status=JobStatus.FAILED,
                event_type=JobEventType.FAILED,
                job_repo=self.job_repo,
                event_repo=self.event_repo,
                event_payload={"error": "Something goes wrong during executing program."},
                job_payload=job.payload,
                error=type(ex).__name__,
            )

        logger.info(
            "Legacy webhook dispatch requested",
            extra={
                "event": "legacy_webhook_dispatch_requested",
                "job_id": job.id,
            },
        )
        await self.webhook_service.dispatch_job_event(job_id=job.id)
        logger.info(
            "Legacy job execution finished",
            extra={
                "event": "legacy_job_execution_finished",
                "job_id": job.id,
                "job_status": final_status,
            },
        )
