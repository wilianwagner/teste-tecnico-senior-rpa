from typing import Protocol

from pydantic import BaseModel

from app.core.enums import JobSource
from app.schemas.crawl import HockeyTeamData, OscarFilmData


class CrawlResult(BaseModel):
    """Rows collected in one crawl; each crawler fills only its own section."""

    hockey: list[HockeyTeamData] = []
    oscar: list[OscarFilmData] = []

    @property
    def total_records(self) -> int:
        return len(self.hockey) + len(self.oscar)


class Crawler(Protocol):
    """A data source collector.

    Implementations fetch everything the source offers and return it in one
    result; partial data must not be returned silently — failures raise
    CrawlerError so the job is retried or marked failed.
    """

    source: JobSource

    def crawl(self) -> CrawlResult: ...
