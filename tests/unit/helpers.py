from app.core.enums import JobSource
from app.crawlers.base import CrawlResult


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
