from datetime import datetime, timezone

from sqlalchemy import select

from main_service.core.logging import get_logger
from main_service.db.session import AsyncSessionLocal
from main_service.models.job_models import Job, JobEvent
from main_service.repositories.event_repository import EventRepository
from main_service.repositories.jobs_repository import JobsRepository
from main_service.schemas.enums import JobEventType, JobStatus


logger = get_logger(__name__)


def _should_log_transition(job_status: JobStatus, event_type: JobEventType, error: str | None) -> bool:
    if error is not None:
        return True

    return event_type in {
        JobEventType.QUEUED,
        JobEventType.FINISHED,
        JobEventType.FAILED,
    } or job_status in {
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    }


async def transition_job(
    job_id: int,
    job_status: JobStatus,
    event_type: JobEventType,
    job_repo: JobsRepository,
    event_repo: EventRepository,
    job_payload: str | None = None,
    event_payload: dict | None = None,
    result: str | None = None,
    error: str | None = None,
):
    async with AsyncSessionLocal() as session:
        try:
            job = await job_repo.find_job_by_id(job_id, session)
            if job is None:
                logger.warning(
                    "Job transition skipped because job was not found",
                    extra={
                        "event": "job_transition_skipped",
                        "job_id": job_id,
                        "job_status": job_status,
                        "event_type": event_type,
                    },
                )
                return

            job.status = job_status
            job.payload = job_payload if job_payload is not None else job.payload
            job.result = result
            job.error = error
            define_time_fields(job)

            result_db = await session.execute(
                select(JobEvent.sequence_no)
                .where(JobEvent.job_id == job_id)
                .order_by(JobEvent.sequence_no.desc())
            )

            last_sequence_no = result_db.scalars().first()

            event = JobEvent(
                job_id=job.id,
                event_type=event_type,
                sequence_no=1 if last_sequence_no is None else last_sequence_no + 1,
                payload=event_payload if event_payload is not None else {"job_payload": job.payload},
            )

            await event_repo.add(event, session)
            await session.commit()
            await session.refresh(job)
            await session.refresh(event)

            if _should_log_transition(job_status, event_type, error):
                logger_method = logger.warning if error is not None or job_status == JobStatus.FAILED else logger.info
                logger_method(
                    "Job transitioned",
                    extra={
                        "event": "job_transitioned",
                        "job_id": job.id,
                        "job_status": job.status,
                        "event_type": event.event_type,
                        "sequence_no": event.sequence_no,
                        "error_message": error,
                    },
                )

            return job

        except Exception:
            await session.rollback()
            logger.exception(
                "Job transition failed",
                extra={
                    "event": "job_transition_failed",
                    "job_id": job_id,
                    "job_status": job_status,
                    "event_type": event_type,
                },
            )
            raise


def define_time_fields(job: Job) -> Job:
    now = datetime.now(timezone.utc)

    match job.status:
        case JobStatus.PENDING:
            pass
        case JobStatus.QUEUED:
            pass
        case JobStatus.RUNNING if job.started_at is None:
            job.started_at = now
        case JobStatus.RUNNING:
            job.updated_at = now
        case JobStatus.SUCCEEDED | JobStatus.FAILED | JobStatus.CANCELLED if job.finished_at is None:
            job.finished_at = now

    return job
