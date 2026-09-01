import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import Settings
from app.core.enums import JobSource
from app.core.exceptions import CrawlerError
from app.core.logging import get_logger
from app.crawlers.base import CrawlResult
from app.crawlers.hockey.parser import parse_teams, parse_total_pages

logger = get_logger(__name__)

USER_AGENT = "rpa-crawler/0.1"


class HockeyCrawler:
    source = JobSource.HOCKEY

    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.hockey_base_url
        self.per_page = settings.hockey_per_page
        self.timeout = settings.http_timeout_seconds

    def crawl(self) -> CrawlResult:
        try:
            with httpx.Client(timeout=self.timeout, headers={"User-Agent": USER_AGENT}) as client:
                first_page = self._fetch_page(client, 1)
                teams = parse_teams(first_page)
                total_pages = parse_total_pages(first_page)
                logger.info("hockey_crawl_started", total_pages=total_pages)

                for page_num in range(2, total_pages + 1):
                    teams.extend(parse_teams(self._fetch_page(client, page_num)))
        except httpx.HTTPError as exc:
            raise CrawlerError(f"Failed to fetch hockey pages: {exc}") from exc

        logger.info("hockey_crawl_finished", records=len(teams))
        return CrawlResult(hockey=teams)

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
