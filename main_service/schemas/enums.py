import enum


class JobStatus(enum.Enum):
    PENDING = 1
    QUEUED = 2
    RUNNING = 3
    SUCCEEDED = 4
    FAILED = 5
    CANCELLED = 6


class JobEventType(enum.Enum):
    CREATED = 1
    QUEUED = 2
    STARTED = 3
    FINISHED = 4
    FAILED = 5