from fastapi import Request
from fastapi.responses import JSONResponse 
from main_service.core.exception.exception import AppException

async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        headers={"X-Correlation-ID": request.state.correlation_id},
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details
            }
        }
    )