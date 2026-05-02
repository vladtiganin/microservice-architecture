from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, exists
from sqlalchemy.exc import IntegrityError

from main_service.models.user_models import User
from main_service.core.exception.exception import UserAlreadyRegisteredError


class UsersRepository:
    def __init__(self):
        pass


    async def user_exists(self, email: str, session: AsyncSession) -> bool:
        statement = select(exists().where(User.email == email))
        res = await session.execute(statement)
        return res.scalar()
    

    async def add_user(self, new_user: User, session: AsyncSession) -> User:
        try:
            session.add(new_user)
            await session.flush()
            await session.refresh(new_user)
            return new_user
        except IntegrityError:
            await session.rollback()
            raise UserAlreadyRegisteredError(new_user.email)
        

    async def get_user(self, email: str, session: AsyncSession) -> User:
        statement = select(User).where(User.email == email)
        res = await session.execute(statement)
        return res.scalar()
    

    async def get_by_id(self, user_id: int, session: AsyncSession) -> User:
        statement = select(User).where(User.id == user_id)
        res = await session.execute(statement)
        return res.scalar()
            