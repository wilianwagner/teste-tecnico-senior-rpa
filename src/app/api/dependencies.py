from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.messaging.publisher import CrawlJobPublisher
from app.services.jobs import JobService


def get_db(request: Request) -> Iterator[Session]:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        yield session


def get_publisher(request: Request) -> CrawlJobPublisher:
    publisher: CrawlJobPublisher = request.app.state.publisher
    return publisher


def get_job_service(
    session: Session = Depends(get_db),
    publisher: CrawlJobPublisher = Depends(get_publisher),
) -> JobService:
    return JobService(session, publisher)
