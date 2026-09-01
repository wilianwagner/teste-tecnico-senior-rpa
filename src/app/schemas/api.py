import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import JobSource, JobStatus


class Page[ItemT](BaseModel):
    items: list[ItemT]
    total: int
    limit: int
    offset: int


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: JobSource
    status: JobStatus
    attempts: int
    records_collected: int | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobEnqueuedOut(BaseModel):
    job_id: uuid.UUID
    source: JobSource
    status: JobStatus


class HockeyTeamStatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    team_name: str
    year: int
    wins: int
    losses: int
    ot_losses: int | None
    win_pct: float
    goals_for: int
    goals_against: int
    goal_diff: int


class OscarFilmOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    title: str
    nominations: int
    awards: int
    best_picture: bool


class JobResultsOut(BaseModel):
    job_id: uuid.UUID
    source: JobSource
    status: JobStatus
    records_collected: int | None
    error_message: str | None
    hockey: Page[HockeyTeamStatOut] | None = None
    oscar: Page[OscarFilmOut] | None = None


class HockeySnapshotOut(Page[HockeyTeamStatOut]):
    job_id: uuid.UUID | None
    collected_at: datetime | None


class OscarSnapshotOut(Page[OscarFilmOut]):
    job_id: uuid.UUID | None
    collected_at: datetime | None


class HealthOut(BaseModel):
    status: str
    database: bool
    broker: bool
