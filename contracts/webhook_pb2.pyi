import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class WebhookPayload(_message.Message):
    __slots__ = ("job_id", "job_status", "finished_at")
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    JOB_STATUS_FIELD_NUMBER: _ClassVar[int]
    FINISHED_AT_FIELD_NUMBER: _ClassVar[int]
    job_id: int
    job_status: str
    finished_at: _timestamp_pb2.Timestamp
    def __init__(self, job_id: _Optional[int] = ..., job_status: _Optional[str] = ..., finished_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class SendWebhookRequest(_message.Message):
    __slots__ = ("webhook_id", "target_url", "payload", "secret")
    WEBHOOK_ID_FIELD_NUMBER: _ClassVar[int]
    TARGET_URL_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    SECRET_FIELD_NUMBER: _ClassVar[int]
    webhook_id: int
    target_url: str
    payload: WebhookPayload
    secret: str
    def __init__(self, webhook_id: _Optional[int] = ..., target_url: _Optional[str] = ..., payload: _Optional[_Union[WebhookPayload, _Mapping]] = ..., secret: _Optional[str] = ...) -> None: ...

class SendWebhookResponse(_message.Message):
    __slots__ = ("webhook_id", "status", "error")
    WEBHOOK_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    webhook_id: int
    status: str
    error: str
    def __init__(self, webhook_id: _Optional[int] = ..., status: _Optional[str] = ..., error: _Optional[str] = ...) -> None: ...
