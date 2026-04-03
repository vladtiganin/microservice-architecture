from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from main_service.models.job_models import Job


class JobsRepository:
    def __init__(self):
        self.storage = []

    async def get(self, session: AsyncSession, skip: int = 0, limit: int = 10) -> list[Job]:
        statement = select(Job).order_by(Job.id).offset(skip).limit(limit)
        res = await session.execute(statement)
        return res.scalars().all()

    async def add(self, job: Job, session: AsyncSession) -> dict:
        session.add(job)
        await session.flush()
        return job


    async def find_job_by_id(self, job_id: int, session: AsyncSession) -> Job:
        statement = select(Job).where(Job.id == job_id)
        res = await session.execute(statement)
        return res.scalar_one_or_none()
