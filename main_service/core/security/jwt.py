from datetime import datetime, timezone, timedelta
from jose import jwt, JWTError

from main_service.config import settings
from main_service.core.exception.exception import UnauthorizedError
from main_service.core.logging.logging import get_logger

ALGORITHM = "HS256"
logger = get_logger(__name__)

def create_access_tooken(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=30)

    payload = {
        "sub": str(user_id),
        "exp": expire,
        "token_type": "access",
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=ALGORITHM
    )


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[ALGORITHM]
        )
    except JWTError:
        logger.warning(
            "Access token rejected because it could not be decoded",
            extra={
                "event": "access_token_rejected",
                "reason": "decode_failed",
            },
        )
        raise UnauthorizedError()
    
    if payload.get("token_type") != "access":
        logger.warning(
            "Access token rejected because token type is invalid",
            extra={
                "event": "access_token_rejected",
                "reason": "invalid_token_type",
            },
        )
        raise UnauthorizedError()
    
    return payload





