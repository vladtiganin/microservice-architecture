from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uuid

from main_service.api import jobs_api
from main_service.api import webhook_api
from main_service.core.logging.logging import *
from main_service.core.context.context import context_correlation_id
from main_service.core.exception.exception_handler import app_exception_handler
from main_service.core.exception.exception import AppException

app = FastAPI(
    title="Job Processing Platform",
    version="1.0.0"
)

app.add_exception_handler(AppException, app_exception_handler)

configure_logging("main_service", disable_uvicorn_access=True)
logger = get_logger(__name__)


@app.middleware("http")
async def log_http_requests(request: Request, call_next):
    started_at = perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        logger.exception(
            "HTTP request failed",
            extra={
                "event": "http_request_failed",
                "method": request.method,
                "path": request.url.path,
                "duration_ms": duration_ms,
            },
        )
        raise

    duration_ms = round((perf_counter() - started_at) * 1000, 2)
    logger.info(
        "HTTP request completed",
        extra={
            "event": "http_request_completed",
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    request.state.correlation_id = correlation_id

    token = context_correlation_id.set(correlation_id)
    try:
        response = await call_next(request)
    finally:
        context_correlation_id.reset(token)
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(jobs_api.router)
app.include_router(webhook_api.router)


@app.get("/")
def root():
    return {"status": "ok"}
