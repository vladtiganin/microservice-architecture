from main_service.core.exception.exception_enum import ExceptionCode

class AppException(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict | None = None
    ):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


class JobNotFoundError(AppException):
    def __init__(self, job_id: int):
        super().__init__(
            status_code=404,
            code=ExceptionCode.JOB_NOT_FOUND,
            message=f"Job with id {job_id} not found",
            details={"job_id": job_id}
        )


class WebhookNotFoundError(AppException):
    def __init__(self, webhook_id: int):
        super().__init__(
            status_code=404,
            code=ExceptionCode.WEBHOOK_NOT_FOUND,
            message=f"Webhook with id {webhook_id} not found",
            details={"webhook_id": webhook_id}
        )


class JobCreateError(AppException):
    def __init__(self, job_type: str):
        super().__init__(
            status_code=500,
            code=ExceptionCode.JOB_CREATE_ERROR,
            message="Failed to create job",
            details={"job_type": job_type}
        )


class WebhookCreateError(AppException):
    def __init__(self, job_id: int):
        super().__init__(
            status_code=500,
            code=ExceptionCode.WEBHOOK_CREATE_ERROR,
            message="Failed to create webhook",
            details={"job_id": job_id}
        )


class WebhookDeleteError(AppException):
    def __init__(self, webhook_id: int):
        super().__init__(
            status_code=500,
            code=ExceptionCode.WEBHOOK_DELETE_ERROR,
            message=f"Failed to delete webhook with id {webhook_id}",
            details={
                "webhook_id": webhook_id
            }
        )


class RegistraiteUserError(AppException):
    def __init__(self, user_email: str):
        super().__init__(
            status_code=500,
            code=ExceptionCode.USER_REGISTRAITE_ERROR,
            message=f"Failed to registraite user",
            details={
                "user_email": user_email
            }
        )


class UserAlreadyRegisteredError(AppException):
    def __init__(self, user_email: str):
        super().__init__(
            status_code=409,
            code=ExceptionCode.USER_EXISTS_ERROR,
            message=f"User with email({user_email}) already exists",
            details={
                "user_email": user_email
            }
        )


class InvalidCredentialsError(AppException):
    def __init__(self):
        super().__init__(
            status_code=401,
            code=ExceptionCode.INVALID_CREDENTIALS_ERROR,
            message=f"Invalid Credentials",
            details={}
        )


class UnauthorizedError(AppException):
    def __init__(self):
        super().__init__(
            status_code=401,
            code=ExceptionCode.UNAUTHORIZED_ERROR,
            message="User unauthorized",
            details={}
        )
