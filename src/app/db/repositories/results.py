import uuid
from collections.abc import Sequence

from sqlalchemy import Select, delete, func, insert, select
from sqlalchemy.orm import Session

from app.core.enums import JobSource, JobStatus
from app.db.models import HockeyTeamStat, Job, OscarFilm
from app.schemas.crawl import HockeyTeamData, OscarFilmData


class ResultRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_hockey(self, job_id: uuid.UUID, rows: Sequence[HockeyTeamData]) -> int:
        """Replace the job's hockey rows (delete + bulk insert), keeping reruns idempotent."""
        self.session.execute(delete(HockeyTeamStat).where(HockeyTeamStat.job_id == job_id))
        if rows:
            self.session.execute(
                insert(HockeyTeamStat),
                [{"job_id": job_id, **row.model_dump()} for row in rows],
            )
        return len(rows)

    def replace_oscar(self, job_id: uuid.UUID, rows: Sequence[OscarFilmData]) -> int:
        """Replace the job's oscar rows (delete + bulk insert), keeping reruns idempotent."""
        self.session.execute(delete(OscarFilm).where(OscarFilm.job_id == job_id))
        if rows:
            self.session.execute(
                insert(OscarFilm),
                [{"job_id": job_id, **row.model_dump()} for row in rows],
            )
        return len(rows)

    def list_hockey_for_job(
        self, job_id: uuid.UUID, *, limit: int = 100, offset: int = 0
    ) -> tuple[list[HockeyTeamStat], int]:
        stmt = select(HockeyTeamStat).where(HockeyTeamStat.job_id == job_id)
        return self._paginate_hockey(stmt, limit=limit, offset=offset)

    def list_oscar_for_job(
        self, job_id: uuid.UUID, *, limit: int = 100, offset: int = 0
    ) -> tuple[list[OscarFilm], int]:
        stmt = select(OscarFilm).where(OscarFilm.job_id == job_id)
        return self._paginate_oscar(stmt, limit=limit, offset=offset)

    def latest_hockey(
        self,
        *,
        year: int | None = None,
        team: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[Job | None, list[HockeyTeamStat], int]:
        """Snapshot: hockey rows of the most recent completed collection.

        Considers jobs with source `hockey` or `all`; running/failed jobs never
        become the snapshot. Returns (None, [], 0) before the first completion.
        """
        job = self._latest_completed_job((JobSource.HOCKEY, JobSource.ALL))
        if job is None:
            return None, [], 0

        stmt = select(HockeyTeamStat).where(HockeyTeamStat.job_id == job.id)
        if year is not None:
            stmt = stmt.where(HockeyTeamStat.year == year)
        if team is not None:
            stmt = stmt.where(HockeyTeamStat.team_name.ilike(f"%{team}%"))

        items, total = self._paginate_hockey(stmt, limit=limit, offset=offset)
        return job, items, total

    def latest_oscar(
        self,
        *,
        year: int | None = None,
        title: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[Job | None, list[OscarFilm], int]:
        """Snapshot: oscar rows of the most recent completed collection.

        Considers jobs with source `oscar` or `all`; running/failed jobs never
        become the snapshot. Returns (None, [], 0) before the first completion.
        """
        job = self._latest_completed_job((JobSource.OSCAR, JobSource.ALL))
        if job is None:
            return None, [], 0

        stmt = select(OscarFilm).where(OscarFilm.job_id == job.id)
        if year is not None:
            stmt = stmt.where(OscarFilm.year == year)
        if title is not None:
            stmt = stmt.where(OscarFilm.title.ilike(f"%{title}%"))

        items, total = self._paginate_oscar(stmt, limit=limit, offset=offset)
        return job, items, total

    def _latest_completed_job(self, sources: tuple[JobSource, ...]) -> Job | None:
        return self.session.scalars(
            select(Job)
            .where(Job.status == JobStatus.COMPLETED, Job.source.in_(sources))
            .order_by(Job.finished_at.desc())
            .limit(1)
        ).first()

    def _paginate_hockey(
        self, stmt: Select[tuple[HockeyTeamStat]], *, limit: int, offset: int
    ) -> tuple[list[HockeyTeamStat], int]:
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = self.session.scalars(
            stmt.order_by(HockeyTeamStat.year, HockeyTeamStat.team_name).limit(limit).offset(offset)
        ).all()
        return list(items), total

    def _paginate_oscar(
        self, stmt: Select[tuple[OscarFilm]], *, limit: int, offset: int
    ) -> tuple[list[OscarFilm], int]:
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = self.session.scalars(
            stmt.order_by(OscarFilm.year.desc(), OscarFilm.title).limit(limit).offset(offset)
        ).all()
        return list(items), total
