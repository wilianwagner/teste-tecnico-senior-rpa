import pytest
from sqlalchemy import Engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.enums import JobSource, JobStatus
from app.db.repositories.jobs import JobRepository
from app.db.repositories.results import ResultRepository
from app.schemas.crawl import HockeyTeamData, OscarFilmData

pytestmark = pytest.mark.integration

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
        team_name="Chicago Blackhawks",
        year=1991,
        wins=36,
        losses=29,
        ot_losses=None,
        win_pct=0.45,
        goals_for=257,
        goals_against=236,
        goal_diff=21,
    ),
]

OSCAR_ROWS = [
    OscarFilmData(year=2015, title="Spotlight", nominations=6, awards=2, best_picture=True),
    OscarFilmData(year=2015, title="Mad Max: Fury Road", nominations=10, awards=6),
]


def test_migration_creates_expected_schema(migrated_engine: Engine) -> None:
    tables = set(inspect(migrated_engine).get_table_names())

    assert {"jobs", "hockey_team_stats", "oscar_films", "alembic_version"} <= tables


def test_job_lifecycle_roundtrip(db_session_factory: sessionmaker[Session]) -> None:
    with db_session_factory() as session:
        repo = JobRepository(session)
        job = repo.create(JobSource.HOCKEY)
        session.commit()
        job_id = job.id

    with db_session_factory() as session:
        repo = JobRepository(session)
        job = repo.get(job_id)
        assert job is not None
        repo.mark_running(job)
        repo.mark_completed(job, records_collected=42)
        session.commit()

    with db_session_factory() as session:
        stored_status = session.execute(
            text("SELECT status FROM jobs WHERE id = :job_id"), {"job_id": job_id}
        ).scalar_one()
        assert stored_status == "completed"

        completed, total = JobRepository(session).list(status=JobStatus.COMPLETED)
        assert total == 1
        assert completed[0].records_collected == 42
        assert completed[0].attempts == 1


def test_latest_snapshot_tracks_most_recent_completed_job(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory() as session:
        jobs = JobRepository(session)
        results = ResultRepository(session)

        old_job = jobs.create(JobSource.HOCKEY)
        results.replace_hockey(old_job.id, HOCKEY_ROWS)
        jobs.mark_running(old_job)
        jobs.mark_completed(old_job, 2)
        session.commit()

        new_job = jobs.create(JobSource.ALL)
        results.replace_hockey(new_job.id, [HOCKEY_ROWS[0]])
        jobs.mark_running(new_job)
        jobs.mark_completed(new_job, 1)
        session.commit()

        running_job = jobs.create(JobSource.HOCKEY)
        jobs.mark_running(running_job)
        session.commit()

        job, items, total = results.latest_hockey()
        assert job is not None
        assert job.id == new_job.id
        assert total == 1
        assert items[0].team_name == "Boston Bruins"


def test_snapshot_filters_use_case_insensitive_match(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory() as session:
        jobs = JobRepository(session)
        results = ResultRepository(session)
        job = jobs.create(JobSource.OSCAR)
        results.replace_oscar(job.id, OSCAR_ROWS)
        jobs.mark_running(job)
        jobs.mark_completed(job, len(OSCAR_ROWS))
        session.commit()

        _, items, total = results.latest_oscar(title="mad max")
        assert total == 1
        assert items[0].title == "Mad Max: Fury Road"

        _, items, total = results.latest_oscar(year=2015)
        assert total == 2


def test_replace_results_is_idempotent_per_job(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory() as session:
        jobs = JobRepository(session)
        results = ResultRepository(session)
        job = jobs.create(JobSource.HOCKEY)
        results.replace_hockey(job.id, HOCKEY_ROWS)
        session.commit()
        results.replace_hockey(job.id, HOCKEY_ROWS)
        session.commit()

        _, total = results.list_hockey_for_job(job.id)
        assert total == len(HOCKEY_ROWS)


def test_deleting_job_cascades_to_results(db_session_factory: sessionmaker[Session]) -> None:
    with db_session_factory() as session:
        jobs = JobRepository(session)
        results = ResultRepository(session)
        job = jobs.create(JobSource.HOCKEY)
        results.replace_hockey(job.id, HOCKEY_ROWS)
        session.commit()
        job_id = job.id

        session.execute(text("DELETE FROM jobs WHERE id = :job_id"), {"job_id": job_id})
        session.commit()

        remaining = session.execute(
            text("SELECT count(*) FROM hockey_team_stats WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).scalar_one()
        assert remaining == 0
