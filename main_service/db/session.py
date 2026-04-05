from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from main_service.config import settings


engine = create_async_engine(
    settings.db_dns,
    echo=True,
)

AsyncSessionLocal = async_sessionmaker(engine)
