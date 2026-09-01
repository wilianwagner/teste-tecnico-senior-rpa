import uuid

from pydantic import BaseModel

from app.core.enums import JobSource


class CrawlJobMessage(BaseModel):
    """Queue payload: which job to run and which source it targets."""

    job_id: uuid.UUID
    source: JobSource

    def to_bytes(self) -> bytes:
        return self.model_dump_json().encode("utf-8")
