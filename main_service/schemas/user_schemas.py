from pydantic import BaseModel, EmailStr
from typing import Literal

from main_service.schemas.enums import UserRagistraiteStatus, UserLoginStatus


class RegistraiteUserRequest(BaseModel):
    email: EmailStr
    password: str


class RegistraiteUserResponse(BaseModel):
    status: UserRagistraiteStatus
    message: str


class LoginUserRequest(BaseModel):
    email: EmailStr
    password: str  


class LoginUserResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"]