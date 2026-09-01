from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_job_service
from app.core.enums import JobSource
from app.schemas.api import JobEnqueuedOut
from app.services.jobs import JobService

router = APIRouter(prefix="/crawl", tags=["crawl"])


@router.post(
    "/{source}",
    response_model=JobEnqueuedOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Schedule a crawl job",
    description=(
        "Creates a job in `pending` state, publishes a message to RabbitMQ and returns "
        "immediately with the job id. Use `source=all` to collect both sources in a "
        "single job. Track progress via `GET /jobs/{job_id}`."
    ),
    responses={
        503: {"description": "Job could not be published to the broker (marked as failed)."},
    },
)
async def schedule_crawl(
    source: JobSource, service: JobService = Depends(get_job_service)
) -> JobEnqueuedOut:
    job = await service.enqueue(source)
    return JobEnqueuedOut(job_id=job.id, source=job.source, status=job.status)
