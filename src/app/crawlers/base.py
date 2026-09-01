from typing import Protocol

from pydantic import BaseModel

from app.core.enums import JobSource
from app.schemas.crawl import HockeyTeamData, OscarFilmData


class CrawlResult(BaseModel):
    hockey: list[HockeyTeamData] = []
    oscar: list[OscarFilmData] = []

    @property
    def total_records(self) -> int:
        return len(self.hockey) + len(self.oscar)


class Crawler(Protocol):
    source: JobSource

    def crawl(self) -> CrawlResult: ...
