from typing import Any

import pytest
from selenium.common.exceptions import StaleElementReferenceException, WebDriverException

from app.core.config import Settings
from app.core.exceptions import CrawlerError
from app.crawlers.oscar import crawler as oscar_module
from app.crawlers.oscar.crawler import OscarCrawler
from app.schemas.crawl import OscarFilmData


class FakeElement:
    def __init__(self, *, stale: bool = False, displayed: bool = False) -> None:
        self.stale = stale
        self.displayed = displayed

    def is_enabled(self) -> bool:
        if self.stale:
            raise StaleElementReferenceException("element is stale")
        return True

    def is_displayed(self) -> bool:
        return self.displayed


class FakeDriver:
    def __init__(self, *, loading_displayed: bool, film_rows: int) -> None:
        self.loading = FakeElement(displayed=loading_displayed)
        self.rows = [FakeElement() for _ in range(film_rows)]
        self.quit_called = False

    def find_element(self, by: str, value: str) -> FakeElement:
        return self.loading

    def find_elements(self, by: str, value: str) -> list[FakeElement]:
        return self.rows

    def quit(self) -> None:
        self.quit_called = True


class TestTableReady:
    def test_waits_while_previous_rows_are_still_attached(self) -> None:
        driver = FakeDriver(loading_displayed=False, film_rows=3)

        assert OscarCrawler._table_ready(driver, FakeElement(stale=False)) is False  # type: ignore[arg-type]

    def test_waits_while_loading_spinner_is_visible(self) -> None:
        driver = FakeDriver(loading_displayed=True, film_rows=3)

        assert OscarCrawler._table_ready(driver, FakeElement(stale=True)) is False  # type: ignore[arg-type]

    def test_waits_until_rows_exist(self) -> None:
        driver = FakeDriver(loading_displayed=False, film_rows=0)

        assert OscarCrawler._table_ready(driver, None) is False  # type: ignore[arg-type]

    def test_ready_when_stale_previous_row_hidden_spinner_and_rows(self) -> None:
        driver = FakeDriver(loading_displayed=False, film_rows=3)

        assert OscarCrawler._table_ready(driver, FakeElement(stale=True)) is True  # type: ignore[arg-type]

    def test_ready_on_first_year_without_previous_rows(self) -> None:
        driver = FakeDriver(loading_displayed=False, film_rows=1)

        assert OscarCrawler._table_ready(driver, None) is True  # type: ignore[arg-type]


class TestBuildDriver:
    def test_uses_remote_webdriver_when_url_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_remote(**kwargs: Any) -> str:
            captured.update(kwargs)
            return "remote-driver"

        monkeypatch.setattr(oscar_module.webdriver, "Remote", fake_remote)
        crawler = OscarCrawler(Settings(selenium_remote_url="http://grid:4444/wd/hub"))

        assert crawler._build_driver() == "remote-driver"
        assert captured["command_executor"] == "http://grid:4444/wd/hub"
        assert "--headless=new" in captured["options"].arguments

    def test_uses_local_chromedriver_path_when_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_chrome(**kwargs: Any) -> str:
            captured.update(kwargs)
            return "local-driver"

        monkeypatch.setattr(oscar_module.webdriver, "Chrome", fake_chrome)
        crawler = OscarCrawler(
            Settings(
                selenium_remote_url="",
                chromedriver_path="/usr/bin/chromedriver",
                chrome_executable_path="/usr/bin/chromium",
            )
        )

        assert crawler._build_driver() == "local-driver"
        assert captured["service"].path == "/usr/bin/chromedriver"
        assert captured["options"].binary_location == "/usr/bin/chromium"


class TestCrawl:
    def test_driver_startup_failure_becomes_crawler_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        crawler = OscarCrawler(Settings())
        monkeypatch.setattr(
            crawler,
            "_build_driver",
            lambda: (_ for _ in ()).throw(WebDriverException("no browser")),
        )

        with pytest.raises(CrawlerError, match="Failed to start browser session"):
            crawler.crawl()

    def test_browser_is_closed_even_when_collection_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        crawler = OscarCrawler(Settings())
        driver = FakeDriver(loading_displayed=False, film_rows=0)
        monkeypatch.setattr(crawler, "_build_driver", lambda: driver)
        monkeypatch.setattr(
            crawler,
            "_collect_all_years",
            lambda _driver: (_ for _ in ()).throw(WebDriverException("timeout")),
        )

        with pytest.raises(CrawlerError, match="Failed to crawl oscar page"):
            crawler.crawl()

        assert driver.quit_called

    def test_successful_collection_returns_films_and_quits_browser(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        crawler = OscarCrawler(Settings())
        driver = FakeDriver(loading_displayed=False, film_rows=1)
        films = [
            OscarFilmData(year=2015, title="Spotlight", nominations=6, awards=2, best_picture=True)
        ]
        monkeypatch.setattr(crawler, "_build_driver", lambda: driver)
        monkeypatch.setattr(crawler, "_collect_all_years", lambda _driver: films)

        result = crawler.crawl()

        assert result.oscar == films
        assert driver.quit_called
