from main_service.models.user_models import User
from main_service.api.dependencies import create_users_repository_instance
from main_service.repositories.users_repository import UsersRepository
from main_service.core.security.jwt import decode_access_token
from main_service.core.exception.exception import UnauthorizedError
from main_service.api.dependencies import get_db_session
from main_service.core.logging.logging import get_logger

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer 
from sqlalchemy.ext.asyncio import AsyncSession


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
logger = get_logger(__name__)


async def get_curr_user(
    token: str = Depends(oauth2_scheme),
    user_repo: UsersRepository = Depends(create_users_repository_instance),
    session: AsyncSession = Depends(get_db_session)
) -> User:
    payload = decode_access_token(token)

    user_id = payload.get("sub")
    if user_id is None:
        logger.warning(
            "Current user rejected because token subject is missing",
            extra={
                "event": "current_user_rejected",
                "reason": "missing_subject",
            },
        )
        raise UnauthorizedError()
    
    try:
        parsed_user_id = int(user_id)
        user = await user_repo.get_by_id(parsed_user_id, session)
        if user is None:
            logger.warning(
                "Current user rejected because user was not found",
                extra={
                    "event": "current_user_rejected",
                    "reason": "user_not_found",
                    "user_id": parsed_user_id,
                },
            )
            raise UnauthorizedError()
    except ValueError:
        logger.warning(
            "Current user rejected because token subject is invalid",
            extra={
                "event": "current_user_rejected",
                "reason": "invalid_subject",
            },
        )
        raise UnauthorizedError()

    return user

