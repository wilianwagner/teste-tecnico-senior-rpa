from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.repositories.results import ResultRepository
from app.schemas.api import HockeySnapshotOut, HockeyTeamStatOut, OscarFilmOut, OscarSnapshotOut

router = APIRouter(prefix="/results", tags=["results"])


@router.get(
    "/hockey",
    response_model=HockeySnapshotOut,
    summary="Hockey data from the most recent completed collection",
)
def get_hockey_results(
    year: int | None = None,
    team: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
) -> HockeySnapshotOut:
    job, items, total = ResultRepository(session).latest_hockey(
        year=year, team=team, limit=limit, offset=offset
    )
    return HockeySnapshotOut(
        job_id=job.id if job else None,
        collected_at=job.finished_at if job else None,
        items=[HockeyTeamStatOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/oscar",
    response_model=OscarSnapshotOut,
    summary="Oscar data from the most recent completed collection",
)
def get_oscar_results(
    year: int | None = None,
    title: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
) -> OscarSnapshotOut:
    job, items, total = ResultRepository(session).latest_oscar(
        year=year, title=title, limit=limit, offset=offset
    )
    return OscarSnapshotOut(
        job_id=job.id if job else None,
        collected_at=job.finished_at if job else None,
        items=[OscarFilmOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
