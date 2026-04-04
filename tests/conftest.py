import pytest
import asyncio
import pytest_asyncio

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool

from main_service.models.job_models import Base

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5433/jobs_test"


@pytest_asyncio.fixture(scope="session")
async def engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(engine):
    SessionLocal = async_sessionmaker(bind=engine,class_=AsyncSession,expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
        await session.rollback()