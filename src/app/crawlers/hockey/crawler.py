from concurrent.futures import ThreadPoolExecutor
from functools import partial

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import Settings
from app.core.enums import JobSource
from app.core.exceptions import CrawlerError
from app.core.logging import get_logger
from app.crawlers.base import CrawlResult
from app.crawlers.hockey.parser import parse_teams, parse_total_pages
from app.schemas.crawl import HockeyTeamData

logger = get_logger(__name__)

USER_AGENT = "rpa-crawler/0.1"


class HockeyCrawler:
    """Collects NHL team stats from the paginated HTML listing.

    Static content, so plain HTTP is used instead of a browser: the first page
    reveals the total page count and the remaining pages are fetched through a
    bounded thread pool, each request with retry and exponential backoff for
    transient network failures. Results keep page order regardless of fetch
    completion order.
    """

    source = JobSource.HOCKEY

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.base_url = settings.hockey_base_url
        self.per_page = settings.hockey_per_page
        self.timeout = settings.http_timeout_seconds
        self.concurrency = settings.hockey_concurrency
        self._transport = transport

    def crawl(self) -> CrawlResult:
        try:
            with httpx.Client(
                timeout=self.timeout,
                headers={"User-Agent": USER_AGENT},
                transport=self._transport,
            ) as client:
                first_page = self._fetch_page(client, 1)
                teams = parse_teams(first_page)
                total_pages = parse_total_pages(first_page)
                logger.info("hockey_crawl_started", total_pages=total_pages)

                teams.extend(self._fetch_remaining_pages(client, total_pages))
        except httpx.HTTPError as exc:
            raise CrawlerError(f"Failed to fetch hockey pages: {exc}") from exc

        logger.info("hockey_crawl_finished", records=len(teams))
        return CrawlResult(hockey=teams)

    def _fetch_remaining_pages(
        self, client: httpx.Client, total_pages: int
    ) -> list[HockeyTeamData]:
        if total_pages <= 1:
            return []

        page_numbers = range(2, total_pages + 1)
        workers = min(self.concurrency, len(page_numbers))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pages = pool.map(partial(self._fetch_page, client), page_numbers)
            return [team for html in pages for team in parse_teams(html)]

    @retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=5),
        reraise=True,
    )
    def _fetch_page(self, client: httpx.Client, page_num: int) -> str:
        response = client.get(
            self.base_url, params={"page_num": page_num, "per_page": self.per_page}
        )
        response.raise_for_status()
        return response.text
