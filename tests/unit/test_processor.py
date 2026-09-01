import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.enums import JobSource, JobStatus
from app.core.exceptions import CrawlerError
from app.crawlers.base import CrawlResult
from app.db.models import HockeyTeamStat, Job, OscarFilm
from app.db.repositories.jobs import JobRepository
from app.messaging.messages import CrawlJobMessage
from app.schemas.crawl import HockeyTeamData, OscarFilmData
from app.worker.processor import JobProcessor, ProcessOutcome
from tests.unit.helpers import StubCrawler

HOCKEY_ROWS = [
    HockeyTeamData(
        team_name="Boston Bruins",
        year=1990,
        wins=44,
        losses=24,
        ot_losses=None,
        win_pct=0.55,
        goals_for=299,
        goals_against=264,
        goal_diff=35,
    ),
    HockeyTeamData(
        team_name="Buffalo Sabres",
        year=1990,
        wins=31,
        losses=30,
        ot_losses=None,
        win_pct=0.388,
        goals_for=292,
        goals_against=278,
        goal_diff=14,
    ),
]

OSCAR_ROWS = [
    OscarFilmData(year=2015, title="Spotlight", nominations=6, awards=2, best_picture=True),
]


def create_job(session_factory: sessionmaker[Session], source: JobSource) -> uuid.UUID:
    with session_factory() as session:
        job = JobRepository(session).create(source)
        session.commit()
        return job.id


def get_job(session_factory: sessionmaker[Session], job_id: uuid.UUID) -> Job:
    with session_factory() as session:
        job = session.get(Job, job_id)
        assert job is not None
        return job


class TestJobProcessorSuccess:
    def test_completes_job_and_persists_records(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        job_id = create_job(session_factory, JobSource.HOCKEY)
        crawler = StubCrawler(JobSource.HOCKEY, CrawlResult(hockey=HOCKEY_ROWS))
        processor = JobProcessor(session_factory, {JobSource.HOCKEY: (crawler,)}, max_attempts=3)

        outcome = processor.process(CrawlJobMessage(job_id=job_id, source=JobSource.HOCKEY))

        assert outcome == ProcessOutcome.COMPLETED
        job = get_job(session_factory, job_id)
        assert job.status == JobStatus.COMPLETED
        assert job.records_collected == 2
        assert job.attempts == 1
        assert job.started_at is not None
        assert job.finished_at is not None
        with session_factory() as session:
            rows = session.scalars(select(HockeyTeamStat)).all()
            assert {row.team_name for row in rows} == {"Boston Bruins", "Buffalo Sabres"}

    def test_all_source_runs_both_crawlers(self, session_factory: sessionmaker[Session]) -> None:
        job_id = create_job(session_factory, JobSource.ALL)
        hockey = StubCrawler(JobSource.HOCKEY, CrawlResult(hockey=HOCKEY_ROWS))
        oscar = StubCrawler(JobSource.OSCAR, CrawlResult(oscar=OSCAR_ROWS))
        processor = JobProcessor(session_factory, {JobSource.ALL: (hockey, oscar)}, max_attempts=3)

        outcome = processor.process(CrawlJobMessage(job_id=job_id, source=JobSource.ALL))

        assert outcome == ProcessOutcome.COMPLETED
        job = get_job(session_factory, job_id)
        assert job.records_collected == 3
        assert hockey.calls == 1
        assert oscar.calls == 1

    def test_reprocessing_replaces_rows_without_duplicates(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        job_id = create_job(session_factory, JobSource.HOCKEY)
        crawler = StubCrawler(JobSource.HOCKEY, CrawlResult(hockey=HOCKEY_ROWS))
        processor = JobProcessor(session_factory, {JobSource.HOCKEY: (crawler,)}, max_attempts=3)
        message = CrawlJobMessage(job_id=job_id, source=JobSource.HOCKEY)

        processor.process(message)
        with session_factory() as session:
            job = session.get(Job, job_id)
            assert job is not None
            job.status = JobStatus.RUNNING
            session.commit()
        processor.process(message)

        with session_factory() as session:
            assert len(session.scalars(select(HockeyTeamStat)).all()) == len(HOCKEY_ROWS)


class TestJobProcessorSkip:
    def test_unknown_job_is_skipped(self, session_factory: sessionmaker[Session]) -> None:
        processor = JobProcessor(session_factory, {}, max_attempts=3)

        outcome = processor.process(CrawlJobMessage(job_id=uuid.uuid4(), source=JobSource.HOCKEY))

        assert outcome == ProcessOutcome.SKIPPED

    def test_completed_job_is_not_reprocessed(self, session_factory: sessionmaker[Session]) -> None:
        job_id = create_job(session_factory, JobSource.HOCKEY)
        crawler = StubCrawler(JobSource.HOCKEY, CrawlResult(hockey=HOCKEY_ROWS))
        processor = JobProcessor(session_factory, {JobSource.HOCKEY: (crawler,)}, max_attempts=3)
        message = CrawlJobMessage(job_id=job_id, source=JobSource.HOCKEY)

        assert processor.process(message) == ProcessOutcome.COMPLETED
        assert processor.process(message) == ProcessOutcome.SKIPPED
        assert crawler.calls == 1


class TestJobProcessorFailure:
    def test_failure_below_max_attempts_schedules_retry(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        job_id = create_job(session_factory, JobSource.HOCKEY)
        crawler = StubCrawler(JobSource.HOCKEY, error=CrawlerError("site is down"))
        processor = JobProcessor(session_factory, {JobSource.HOCKEY: (crawler,)}, max_attempts=3)

        outcome = processor.process(CrawlJobMessage(job_id=job_id, source=JobSource.HOCKEY))

        assert outcome == ProcessOutcome.RETRY
        job = get_job(session_factory, job_id)
        assert job.status == JobStatus.PENDING
        assert job.attempts == 1
        assert job.error_message is not None
        assert "site is down" in job.error_message

    def test_failure_at_max_attempts_marks_job_failed(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        job_id = create_job(session_factory, JobSource.HOCKEY)
        crawler = StubCrawler(JobSource.HOCKEY, error=CrawlerError("site is down"))
        processor = JobProcessor(session_factory, {JobSource.HOCKEY: (crawler,)}, max_attempts=2)
        message = CrawlJobMessage(job_id=job_id, source=JobSource.HOCKEY)

        assert processor.process(message) == ProcessOutcome.RETRY
        assert processor.process(message) == ProcessOutcome.FAILED

        job = get_job(session_factory, job_id)
        assert job.status == JobStatus.FAILED
        assert job.attempts == 2

    def test_partial_failure_keeps_successful_source_data(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        job_id = create_job(session_factory, JobSource.ALL)
        hockey = StubCrawler(JobSource.HOCKEY, CrawlResult(hockey=HOCKEY_ROWS))
        oscar = StubCrawler(JobSource.OSCAR, error=CrawlerError("selenium timeout"))
        processor = JobProcessor(session_factory, {JobSource.ALL: (hockey, oscar)}, max_attempts=1)

        outcome = processor.process(CrawlJobMessage(job_id=job_id, source=JobSource.ALL))

        assert outcome == ProcessOutcome.FAILED
        job = get_job(session_factory, job_id)
        assert job.status == JobStatus.FAILED
        assert job.error_message is not None
        assert "oscar: selenium timeout" in job.error_message
        with session_factory() as session:
            assert len(session.scalars(select(HockeyTeamStat)).all()) == 2
            assert session.scalars(select(OscarFilm)).all() == []
