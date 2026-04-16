from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class ExecuteJobRequest(_message.Message):
    __slots__ = ("job_id", "type", "payload")
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    job_id: int
    type: str
    payload: str
    def __init__(self, job_id: _Optional[int] = ..., type: _Optional[str] = ..., payload: _Optional[str] = ...) -> None: ...

class ExecuteJobResponse(_message.Message):
    __slots__ = ("progress", "status", "result", "error")
    PROGRESS_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    progress: int
    status: str
    result: str
    error: str
    def __init__(self, progress: _Optional[int] = ..., status: _Optional[str] = ..., result: _Optional[str] = ..., error: _Optional[str] = ...) -> None: ...
