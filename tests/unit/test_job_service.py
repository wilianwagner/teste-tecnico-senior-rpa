import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.enums import JobSource, JobStatus
from app.core.exceptions import PublishError
from app.db.models import Job
from app.messaging.messages import CrawlJobMessage
from app.services.jobs import JobService


class FakePublisher:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.published: list[CrawlJobMessage] = []

    async def publish(self, message: CrawlJobMessage) -> None:
        if self.error is not None:
            raise self.error
        self.published.append(message)


class TestEnqueue:
    async def test_creates_pending_job_and_publishes_message(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        publisher = FakePublisher()
        with session_factory() as session:
            service = JobService(session, publisher)

            job = await service.enqueue(JobSource.HOCKEY)

        assert job.status == JobStatus.PENDING
        assert publisher.published == [CrawlJobMessage(job_id=job.id, source=JobSource.HOCKEY)]
        with session_factory() as session:
            persisted = session.get(Job, job.id)
            assert persisted is not None
            assert persisted.source == JobSource.HOCKEY

    async def test_publish_failure_marks_job_failed_and_raises(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        publisher = FakePublisher(error=PublishError("broker unreachable"))
        with session_factory() as session:
            service = JobService(session, publisher)

            with pytest.raises(PublishError):
                await service.enqueue(JobSource.OSCAR)

        with session_factory() as session:
            job = session.scalars(select(Job)).one()
            assert job.status == JobStatus.FAILED
            assert job.error_message is not None
            assert "broker unreachable" in job.error_message
