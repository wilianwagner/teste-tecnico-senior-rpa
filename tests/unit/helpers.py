from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.enums import JobSource
from app.crawlers.base import CrawlResult
from app.main import create_app
from app.messaging.messages import CrawlJobMessage


class FakePublisher:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.published: list[CrawlJobMessage] = []

    async def publish(self, message: CrawlJobMessage) -> None:
        if self.error is not None:
            raise self.error
        self.published.append(message)

    async def ping(self) -> bool:
        return True


def make_client(session_factory: sessionmaker[Session], publisher: FakePublisher) -> TestClient:
    app = create_app(
        Settings(),
        session_factory=session_factory,
        publisher=publisher,  # type: ignore[arg-type]
    )
    return TestClient(app)


class StubCrawler:
    def __init__(
        self,
        source: JobSource,
        result: CrawlResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.source = source
        self.result = result if result is not None else CrawlResult()
        self.error = error
        self.calls = 0

    def crawl(self) -> CrawlResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result
