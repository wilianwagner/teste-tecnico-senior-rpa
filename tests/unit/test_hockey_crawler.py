import httpx
import pytest
from tenacity import wait_none

from app.core.config import Settings
from app.core.exceptions import CrawlerError
from app.crawlers.hockey.crawler import HockeyCrawler


def page_html(page: int, total_pages: int, teams_per_page: int = 2) -> str:
    rows = "".join(
        f"<tr class='team'>"
        f"<td class='name'>Team {page}-{index}</td><td class='year'>1990</td>"
        f"<td class='wins'>10</td><td class='losses'>5</td><td class='ot-losses'></td>"
        f"<td class='pct'>0.5</td><td class='gf'>100</td><td class='ga'>90</td>"
        f"<td class='diff'>10</td></tr>"
        for index in range(teams_per_page)
    )
    links = "".join(
        f"<li><a href='/pages/forms/?page_num={number}'>{number}</a></li>"
        for number in range(1, total_pages + 1)
    )
    return f"<html><body><table>{rows}</table><ul class='pagination'>{links}</ul></body></html>"


class FakeSite:
    def __init__(self, total_pages: int, failures: dict[int, int] | None = None) -> None:
        self.total_pages = total_pages
        self.failures = dict(failures or {})
        self.calls: list[int] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page_num"])
        self.calls.append(page)
        if self.failures.get(page, 0) > 0:
            self.failures[page] -= 1
            return httpx.Response(503)
        return httpx.Response(200, text=page_html(page, self.total_pages))


def build_crawler(site: FakeSite) -> HockeyCrawler:
    return HockeyCrawler(Settings(), transport=httpx.MockTransport(site.handler))


@pytest.fixture(autouse=True)
def _no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(HockeyCrawler._fetch_page.retry, "wait", wait_none())


class TestHockeyCrawler:
    def test_collects_every_page_exactly_once_in_order(self) -> None:
        site = FakeSite(total_pages=3)

        result = build_crawler(site).crawl()

        assert len(result.hockey) == 6
        assert [team.team_name for team in result.hockey] == [
            "Team 1-0",
            "Team 1-1",
            "Team 2-0",
            "Team 2-1",
            "Team 3-0",
            "Team 3-1",
        ]
        assert sorted(site.calls) == [1, 2, 3]

    def test_single_page_listing_fetches_only_once(self) -> None:
        site = FakeSite(total_pages=1)

        result = build_crawler(site).crawl()

        assert len(result.hockey) == 2
        assert site.calls == [1]

    def test_transient_failures_are_retried_until_success(self) -> None:
        site = FakeSite(total_pages=3, failures={2: 2})

        result = build_crawler(site).crawl()

        assert len(result.hockey) == 6
        assert site.calls.count(2) == 3

    def test_persistent_failure_exhausts_retries_and_raises(self) -> None:
        site = FakeSite(total_pages=3, failures={3: 99})

        with pytest.raises(CrawlerError, match="Failed to fetch hockey pages"):
            build_crawler(site).crawl()

        assert site.calls.count(3) == 3
