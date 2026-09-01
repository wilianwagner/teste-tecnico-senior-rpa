import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import JobSource, JobStatus
from app.db.base import Base


def _str_enum(enum_cls: type[StrEnum]) -> SAEnum:
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=20,
        values_callable=lambda e: [member.value for member in e],
    )


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_created_at", "created_at"),
        Index("ix_jobs_status_source_finished_at", "status", "source", "finished_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source: Mapped[JobSource] = mapped_column(_str_enum(JobSource))
    status: Mapped[JobStatus] = mapped_column(_str_enum(JobStatus), default=JobStatus.PENDING)
    attempts: Mapped[int] = mapped_column(default=0)
    records_collected: Mapped[int | None]
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HockeyTeamStat(Base):
    __tablename__ = "hockey_team_stats"
    __table_args__ = (Index("ix_hockey_team_stats_team_name_year", "team_name", "year"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    team_name: Mapped[str] = mapped_column(String(120))
    year: Mapped[int]
    wins: Mapped[int]
    losses: Mapped[int]
    ot_losses: Mapped[int | None]
    win_pct: Mapped[float]
    goals_for: Mapped[int]
    goals_against: Mapped[int]
    goal_diff: Mapped[int]


class OscarFilm(Base):
    __tablename__ = "oscar_films"
    __table_args__ = (Index("ix_oscar_films_year_title", "year", "title"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    year: Mapped[int]
    title: Mapped[str] = mapped_column(String(255))
    nominations: Mapped[int]
    awards: Mapped[int]
    best_picture: Mapped[bool] = mapped_column(default=False)
