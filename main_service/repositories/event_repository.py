from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from main_service.models.job_models import JobEvent

class EventRepository:
    
    async def add(self, eve: JobEvent, session: AsyncSession):
        session.add(eve)
        await session.flush()
        return eve
