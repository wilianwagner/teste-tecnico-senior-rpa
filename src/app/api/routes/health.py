from anyio import to_thread
from fastapi import APIRouter, Request, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.schemas.api import HealthOut

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthOut,
    summary="Service health",
    description="Checks database and broker connectivity.",
    responses={503: {"description": "One or more dependencies are unreachable."}},
)
async def health(request: Request, response: Response) -> HealthOut:
    database_ok = await to_thread.run_sync(_check_database, request)
    broker_ok = await _check_broker(request)

    healthy = database_ok and broker_ok
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthOut(
        status="ok" if healthy else "degraded",
        database=database_ok,
        broker=broker_ok,
    )


def _check_database(request: Request) -> bool:
    try:
        with request.app.state.session_factory() as session:
            session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True


async def _check_broker(request: Request) -> bool:
    try:
        return bool(await request.app.state.publisher.ping())
    except Exception:
        return False
