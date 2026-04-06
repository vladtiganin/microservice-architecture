from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException

from main_service.models.job_models import JobEvent

class EventRepository:
    
    async def add(self, eve: JobEvent, session: AsyncSession):
        session.add(eve)
        await session.flush()
        return eve
    

    async def get(self, job_id: int, session: AsyncSession, skip: int = 0, limit: int = 25) -> list[JobEvent]:
        statement = select(JobEvent).where(JobEvent.job_id==job_id, JobEvent.sequence_no>skip).order_by(JobEvent.sequence_no).limit(limit)
        res = await session.execute(statement)
        return res.scalars().all()