from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from main_service.schemas.user_schemas import *
from main_service.services.auth_service import AuthService
from main_service.models.user_models import User
from main_service.core.security.dependencies import get_curr_user
from main_service.api.dependencies import create_auth_service_instance, get_db_session

router = APIRouter(
    prefix="/auth",
    tags=["auth"]
)


@router.post("/register", response_model=RegistraiteUserResponse)
async def registraite_user(
    body: RegistraiteUserRequest,
    auth_service: AuthService = Depends(create_auth_service_instance),
    session: AsyncSession = Depends(get_db_session),
):
    return await auth_service.register_user(body, session)


@router.post("/login", response_model=LoginUserResponse)
async def login_user(
    req_body: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends(create_auth_service_instance),
    session: AsyncSession = Depends(get_db_session),
):
    body = LoginUserRequest(
        email=req_body.username,
        password=req_body.password
    )
    return await auth_service.login_user(body, session)