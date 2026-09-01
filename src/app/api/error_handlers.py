from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.exceptions import JobNotFoundError, PublishError
from app.core.logging import get_logger

logger = get_logger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(JobNotFoundError)
    async def job_not_found_handler(request: Request, exc: JobNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc)},
        )

    @app.exception_handler(PublishError)
    async def publish_error_handler(request: Request, exc: PublishError) -> JSONResponse:
        logger.error("enqueue_failed", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": f"Failed to enqueue job: {exc}"},
        )
