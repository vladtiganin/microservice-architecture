import json
import logging
import sys
from datetime import datetime, timezone

import pytest

from executor_service.core.logging import JsonFormatter as ExecutorJsonFormatter
from executor_service.core.logging import ServiceFilter as ExecutorServiceFilter
from main_service.core.logging import JsonFormatter as MainJsonFormatter
from main_service.core.logging import ServiceFilter as MainServiceFilter
from main_service.schemas.enums import JobStatus
from webhook_service.core.logging import JsonFormatter as WebhookJsonFormatter
from webhook_service.core.logging import ServiceFilter as WebhookServiceFilter


FORMATTERS = [
    (MainJsonFormatter, MainServiceFilter, "main_service.example", "main_service"),
    (ExecutorJsonFormatter, ExecutorServiceFilter, "executor_service.example", "executor_service"),
    (WebhookJsonFormatter, WebhookServiceFilter, "webhook_service.example", "webhook_service"),
]


@pytest.mark.parametrize(("formatter_cls", "filter_cls", "logger_name", "expected_service"), FORMATTERS)
def test_json_formatter_outputs_standard_and_extra_fields(
    formatter_cls,
    filter_cls,
    logger_name,
    expected_service,
):
    record = logging.LogRecord(
        name=logger_name,
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Structured %s",
        args=("log",),
        exc_info=None,
    )
    record.event = "structured_log_created"
    record.job_id = 7
    record.job_status = JobStatus.RUNNING
    record.finished_at = datetime(2026, 4, 13, 10, 0, tzinfo=timezone.utc)

    filter_cls("fallback").filter(record)
    payload = json.loads(formatter_cls().format(record))

    assert payload["message"] == "Structured log"
    assert payload["event"] == "structured_log_created"
    assert payload["service"] == expected_service
    assert payload["job_id"] == 7
    assert payload["job_status"] == "running"
    assert payload["finished_at"] == "2026-04-13T10:00:00+00:00"
    assert "timestamp" in payload
    assert payload["level"] == "INFO"
    assert payload["logger"] == logger_name


@pytest.mark.parametrize(("formatter_cls", "filter_cls", "logger_name", "expected_service"), FORMATTERS)
def test_json_formatter_defaults_event_when_missing(
    formatter_cls,
    filter_cls,
    logger_name,
    expected_service,
):
    record = logging.LogRecord(
        name=logger_name,
        level=logging.WARNING,
        pathname=__file__,
        lineno=20,
        msg="No explicit event",
        args=(),
        exc_info=None,
    )

    filter_cls("fallback").filter(record)
    payload = json.loads(formatter_cls().format(record))

    assert payload["event"] == "log_record"
    assert payload["service"] == expected_service


@pytest.mark.parametrize(("formatter_cls", "filter_cls", "logger_name", "expected_service"), FORMATTERS)
def test_json_formatter_serializes_exception_fields(
    formatter_cls,
    filter_cls,
    logger_name,
    expected_service,
):
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name=logger_name,
        level=logging.ERROR,
        pathname=__file__,
        lineno=30,
        msg="Formatter failed",
        args=(),
        exc_info=exc_info,
    )
    record.event = "formatter_failed"

    filter_cls("fallback").filter(record)
    payload = json.loads(formatter_cls().format(record))

    assert payload["service"] == expected_service
    assert payload["event"] == "formatter_failed"
    assert payload["error_type"] == "RuntimeError"
    assert payload["error_message"] == "boom"
    assert "RuntimeError: boom" in payload["stack_trace"]
