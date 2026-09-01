import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import JobSource, JobStatus
from app.db.models import Job


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, source: JobSource) -> Job:
        job = Job(source=source, status=JobStatus.PENDING)
        self.session.add(job)
        self.session.flush()
        return job

    def get(self, job_id: uuid.UUID) -> Job | None:
        return self.session.get(Job, job_id)

    def list(
        self,
        *,
        status: JobStatus | None = None,
        source: JobSource | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Job], int]:
        stmt = select(Job)
        if status is not None:
            stmt = stmt.where(Job.status == status)
        if source is not None:
            stmt = stmt.where(Job.source == source)

        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = self.session.scalars(
            stmt.order_by(Job.created_at.desc()).limit(limit).offset(offset)
        ).all()
        return list(items), total

    def mark_running(self, job: Job) -> None:
        """Start (or restart) an execution; the attempt counter bounds retries."""
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        job.attempts += 1
        job.error_message = None

    def mark_completed(self, job: Job, records_collected: int) -> None:
        job.status = JobStatus.COMPLETED
        job.records_collected = records_collected
        job.finished_at = datetime.now(UTC)

    def mark_failed(self, job: Job, error: str) -> None:
        job.status = JobStatus.FAILED
        job.error_message = error
        job.finished_at = datetime.now(UTC)

    def mark_pending_retry(self, job: Job, error: str) -> None:
        """Return the job to pending (message will be redelivered), keeping the error."""
        job.status = JobStatus.PENDING
        job.error_message = error
