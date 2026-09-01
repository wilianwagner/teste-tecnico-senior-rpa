from anyio import to_thread
from sqlalchemy.orm import Session

from app.core.enums import JobSource
from app.core.exceptions import PublishError
from app.core.logging import get_logger
from app.db.models import Job
from app.db.repositories.jobs import JobRepository
from app.messaging.messages import CrawlJobMessage
from app.messaging.publisher import SupportsPublish

logger = get_logger(__name__)


class JobService:
    def __init__(self, session: Session, publisher: SupportsPublish) -> None:
        self.session = session
        self.publisher = publisher

    async def enqueue(self, source: JobSource) -> Job:
        """Create a pending job and publish it to the queue.

        The job row is committed before publishing so a job id always exists;
        if publishing then fails, the job is marked failed with the reason and
        the error propagates for the API to answer 503.
        """
        job = await to_thread.run_sync(self._create_job, source)

        try:
            await self.publisher.publish(CrawlJobMessage(job_id=job.id, source=job.source))
        except PublishError as exc:
            await to_thread.run_sync(self._mark_publish_failure, job, str(exc))
            raise

        logger.info("job_enqueued", job_id=str(job.id), source=job.source.value)
        return job

    def _create_job(self, source: JobSource) -> Job:
        job = JobRepository(self.session).create(source)
        self.session.commit()
        return job

    def _mark_publish_failure(self, job: Job, error: str) -> None:
        JobRepository(self.session).mark_failed(job, f"Failed to publish job message: {error}")
        self.session.commit()
