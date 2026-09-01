from enum import StrEnum


class JobSource(StrEnum):
    HOCKEY = "hockey"
    OSCAR = "oscar"
    ALL = "all"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
