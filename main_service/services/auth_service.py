from main_service.repositories.users_repository import UsersRepository
from main_service.schemas.user_schemas import *
from main_service.schemas.enums import UserRagistraiteStatus, UserLoginStatus
from main_service.core.exception.exception import UserAlreadyRegisteredError, InvalidCredentialsError
from main_service.core.logging.logging import get_logger
from main_service.models.user_models import User
from main_service.core.security.password import hash_password, verify_password
from main_service.core.security.jwt import create_access_tooken

from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone, timedelta


logger = get_logger(__name__)


class AuthService:
    def __init__(self, users_repo: UsersRepository):
        self.users_repo = users_repo

    
    async def register_user(self, body: RegistraiteUserRequest, session: AsyncSession) -> RegistraiteUserResponse:
        logger.info(
            "User registration requested",
            extra={
                "event": "user_registration_requested",
            },
        )

        is_exists = await self.users_repo.user_exists(body.email, session)

        if is_exists:
            logger.warning(
                "User registration rejected because user already exists",
                extra={
                    "event": "user_registration_rejected",
                    "reason": "user_exists",
                },
            )
            raise UserAlreadyRegisteredError(body.email)
         
        new_user = User(
            email=body.email,
            hashed_password=hash_password(body.password)
        )

        try:
            new_user = await self.users_repo.add_user(new_user, session)
            new_user_id = new_user.id
            await session.commit()
        except UserAlreadyRegisteredError:
            logger.warning(
                "User registration rejected because user already exists",
                extra={
                    "event": "user_registration_rejected",
                    "reason": "user_exists",
                },
            )
            raise
        except Exception:
            await session.rollback()
            logger.exception(
                "User registration failed",
                extra={
                    "event": "user_registration_failed",
                },
            )
            raise

        logger.info(
            "User registration succeeded",
            extra={
                "event": "user_registration_succeeded",
                "user_id": new_user_id,
            },
        )

        return {
            "status": UserRagistraiteStatus.SUCCESS,
            "message": "User successfully registraited"
        }


    async def login_user(self, body: LoginUserRequest, session: AsyncSession) -> LoginUserResponse:
        logger.info(
            "User login requested",
            extra={
                "event": "user_login_requested",
            },
        )

        user = await self.users_repo.get_user(body.email, session)
        if user is None:
            logger.warning(
                "User login rejected because user was not found",
                extra={
                    "event": "user_login_rejected",
                    "reason": "user_not_found",
                },
            )
            raise InvalidCredentialsError()

        if not verify_password(body.password, user.hashed_password):
            logger.warning(
                "User login rejected because password is invalid",
                extra={
                    "event": "user_login_rejected",
                    "reason": "invalid_password",
                    "user_id": user.id,
                },
            )
            raise InvalidCredentialsError()

        jwt = create_access_tooken(user.id)

        logger.info(
            "User login succeeded",
            extra={
                "event": "user_login_succeeded",
                "user_id": user.id,
            },
        )

        return {
            "access_token": jwt,
            "token_type": "bearer"
        }





