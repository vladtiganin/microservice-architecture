from contextvars import ContextVar

context_correlation_id: ContextVar[str] = ContextVar(
    "correlation_id", default="-"
)