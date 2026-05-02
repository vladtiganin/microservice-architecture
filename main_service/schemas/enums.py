import enum


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobEventType(str, enum.Enum):
    CREATED = "created"
    QUEUED = "queued"
    STARTED = "started"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"


class WebhookDeliveryStatus(str, enum.Enum):
    SENT = "sent"
    FAILED = "failed"


class UserRagistraiteStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"

    
class UserLoginStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"