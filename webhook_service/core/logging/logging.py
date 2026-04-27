import enum
import json
import logging
from datetime import date, datetime, time, timezone
from logging import Logger, LogRecord
from pathlib import Path
from traceback import format_exception
from typing import Any

from webhook_service.core.context.context import context_correlation_id


STANDARD_LOG_RECORD_FIELDS = {
    "args",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


def _serialize_log_value(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return value.value

    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, BaseException):
        return {
            "type": type(value).__name__,
            "message": str(value),
        }

    if isinstance(value, dict):
        return {
            str(key): _serialize_log_value(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [_serialize_log_value(item) for item in value]

    return value


def _json_default(value: Any) -> Any:
    serialized = _serialize_log_value(value)
    if serialized is value:
        return str(value)

    return serialized


class CorrelationIdFilter(logging.Filter):
    def __init__(self):
        super().__init__()

    def filter(self, record: LogRecord):
        record.correlation_id = context_correlation_id.get()
        return True


class ServiceFilter(logging.Filter):
    def __init__(self, default_service: str):
        super().__init__()
        self.default_service = default_service

    def filter(self, record: LogRecord) -> bool:
        service = getattr(record, "service", None)
        if not service:
            record.service = self._infer_service(record.name)

        event = getattr(record, "event", None)
        if not event:
            record.event = "log_record"

        return True

    def _infer_service(self, logger_name: str) -> str:
        for service_name in ("main_service", "executor_service", "webhook_service"):
            if logger_name == service_name or logger_name.startswith(f"{service_name}."):
                return service_name

        return self.default_service


class JsonFormatter(logging.Formatter):
    def format(self, record: LogRecord) -> str:
        log_record = {
            "timestamp": datetime.fromtimestamp(
                record.created,
                tz=timezone.utc,
            ).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "service": getattr(record, "service", "unknown"),
            "logger": record.name,
            "event": getattr(record, "event", "log_record"),
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key in STANDARD_LOG_RECORD_FIELDS or key in log_record or value is None:
                continue

            log_record[key] = _serialize_log_value(value)

        if record.exc_info:
            exc_type, exc_value, exc_traceback = record.exc_info
            if exc_type is not None:
                log_record.setdefault("error_type", exc_type.__name__)

            if exc_value is not None:
                log_record.setdefault("error_message", str(exc_value))

            log_record["stack_trace"] = "".join(
                format_exception(exc_type, exc_value, exc_traceback)
            ).strip()
        elif record.exc_text:
            log_record["stack_trace"] = record.exc_text

        return json.dumps(log_record, default=_json_default)


def configure_logging(
    service_name: str = "webhook_service",
    *,
    disable_uvicorn_access: bool = False,
) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ServiceFilter(service_name))
    handler.addFilter(CorrelationIdFilter())

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    for logger_name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.disabled = False
        logger.propagate = False

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.setLevel(logging.INFO)
    access_logger.disabled = disable_uvicorn_access
    access_logger.propagate = False
    if not disable_uvicorn_access:
        access_logger.addHandler(handler)


def get_logger(name: str) -> Logger:
    return logging.getLogger(name)
