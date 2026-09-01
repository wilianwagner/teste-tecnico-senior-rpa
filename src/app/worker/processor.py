import uuid
from enum import StrEnum

from sqlalchemy.orm import Session, sessionmaker

from app.core.enums import JobStatus
from app.core.logging import get_logger
from app.crawlers.base import CrawlResult
from app.crawlers.registry import CrawlerRegistry
from app.db.models import Job
from app.db.repositories.jobs import JobRepository
from app.db.repositories.results import ResultRepository
from app.messaging.messages import CrawlJobMessage

logger = get_logger(__name__)


class ProcessOutcome(StrEnum):
    """What the consumer should do with the message after processing."""

    COMPLETED = "completed"
    RETRY = "retry"
    FAILED = "failed"
    SKIPPED = "skipped"


class JobProcessor:
    """Drives the job lifecycle: pending -> running -> completed/failed.

    Retries are bounded by an attempt counter persisted on the job row, so the
    limit survives worker restarts and message redeliveries. Each crawler's
    output is committed as soon as it succeeds; for `all` jobs this keeps the
    data of a successful source even when the other one fails.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        registry: CrawlerRegistry,
        max_attempts: int,
    ) -> None:
        self.session_factory = session_factory
        self.registry = registry
        self.max_attempts = max_attempts

    def process(self, message: CrawlJobMessage) -> ProcessOutcome:
        """Execute one crawl job and report how the message should be settled.

        Idempotent with regard to redeliveries: unknown or already completed
        jobs are skipped (acked), and reruns replace the job's previous rows
        instead of duplicating them.
        """
        with self.session_factory() as session:
            jobs = JobRepository(session)
            job = jobs.get(message.job_id)

            if job is None:
                logger.warning("job_not_found", job_id=str(message.job_id))
                return ProcessOutcome.SKIPPED
            if job.status == JobStatus.COMPLETED:
                logger.info("job_already_completed", job_id=str(job.id))
                return ProcessOutcome.SKIPPED

            jobs.mark_running(job)
            session.commit()
            logger.info(
                "job_started",
                job_id=str(job.id),
                source=job.source.value,
                attempt=job.attempts,
            )

            records, errors = self._run_crawlers(session, job)

            if errors:
                return self._handle_failure(session, jobs, job, "; ".join(errors))

            jobs.mark_completed(job, records)
            session.commit()
            logger.info("job_completed", job_id=str(job.id), records=records)
            return ProcessOutcome.COMPLETED

    def _run_crawlers(self, session: Session, job: Job) -> tuple[int, list[str]]:
        results = ResultRepository(session)
        records = 0
        errors: list[str] = []

        for crawler in self.registry[job.source]:
            try:
                result = crawler.crawl()
            except Exception as exc:
                logger.error(
                    "crawler_failed",
                    job_id=str(job.id),
                    crawler=crawler.source.value,
                    error=str(exc),
                )
                errors.append(f"{crawler.source.value}: {exc}")
                continue

            records += self._persist(results, job.id, result)
            session.commit()

        return records, errors

    def _handle_failure(
        self, session: Session, jobs: JobRepository, job: Job, error: str
    ) -> ProcessOutcome:
        if job.attempts >= self.max_attempts:
            jobs.mark_failed(job, error)
            session.commit()
            logger.error("job_failed", job_id=str(job.id), attempts=job.attempts, error=error)
            return ProcessOutcome.FAILED

        jobs.mark_pending_retry(job, error)
        session.commit()
        logger.warning("job_retry_scheduled", job_id=str(job.id), attempts=job.attempts)
        return ProcessOutcome.RETRY

    @staticmethod
    def _persist(results: ResultRepository, job_id: uuid.UUID, result: CrawlResult) -> int:
        records = 0
        if result.hockey:
            records += results.replace_hockey(job_id, result.hockey)
        if result.oscar:
            records += results.replace_oscar(job_id, result.oscar)
        return records
