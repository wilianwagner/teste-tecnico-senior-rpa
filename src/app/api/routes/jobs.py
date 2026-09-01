import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.enums import JobSource, JobStatus
from app.core.exceptions import JobNotFoundError
from app.db.models import Job
from app.db.repositories.jobs import JobRepository
from app.db.repositories.results import ResultRepository
from app.schemas.api import HockeyTeamStatOut, JobOut, JobResultsOut, OscarFilmOut, Page

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=Page[JobOut], summary="List jobs")
def list_jobs(
    status: JobStatus | None = None,
    source: JobSource | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
) -> Page[JobOut]:
    jobs, total = JobRepository(session).list(
        status=status, source=source, limit=limit, offset=offset
    )
    return Page(
        items=[JobOut.model_validate(job) for job in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{job_id}", response_model=JobOut, summary="Get job status and details")
def get_job(job_id: uuid.UUID, session: Session = Depends(get_db)) -> JobOut:
    job = _get_job_or_raise(session, job_id)
    return JobOut.model_validate(job)


@router.get(
    "/{job_id}/results",
    response_model=JobResultsOut,
    response_model_exclude_none=True,
    summary="Get the data collected by a job",
)
def get_job_results(
    job_id: uuid.UUID,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
) -> JobResultsOut:
    job = _get_job_or_raise(session, job_id)
    results = ResultRepository(session)

    hockey: Page[HockeyTeamStatOut] | None = None
    oscar: Page[OscarFilmOut] | None = None

    if job.source in (JobSource.HOCKEY, JobSource.ALL):
        items, total = results.list_hockey_for_job(job.id, limit=limit, offset=offset)
        hockey = Page(
            items=[HockeyTeamStatOut.model_validate(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )
    if job.source in (JobSource.OSCAR, JobSource.ALL):
        items_oscar, total_oscar = results.list_oscar_for_job(job.id, limit=limit, offset=offset)
        oscar = Page(
            items=[OscarFilmOut.model_validate(item) for item in items_oscar],
            total=total_oscar,
            limit=limit,
            offset=offset,
        )

    return JobResultsOut(
        job_id=job.id,
        source=job.source,
        status=job.status,
        records_collected=job.records_collected,
        error_message=job.error_message,
        hockey=hockey,
        oscar=oscar,
    )


def _get_job_or_raise(session: Session, job_id: uuid.UUID) -> Job:
    job = JobRepository(session).get(job_id)
    if job is None:
        raise JobNotFoundError(str(job_id))
    return job
