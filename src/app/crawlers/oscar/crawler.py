from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, WebDriverException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from app.core.config import Settings
from app.core.enums import JobSource
from app.core.exceptions import CrawlerError
from app.core.logging import get_logger
from app.crawlers.base import CrawlResult
from app.crawlers.oscar.parser import parse_films
from app.schemas.crawl import OscarFilmData

logger = get_logger(__name__)


class OscarCrawler:
    """Collects Oscar film data from the JavaScript-rendered page.

    The table only exists after clicking a year link, so a headless Chromium
    session (remote Selenium node when SELENIUM_REMOTE_URL is set, local
    chromedriver otherwise) clicks through every year and parses the rendered
    DOM. The browser session is always closed, including on failure.
    """

    source = JobSource.OSCAR

    def __init__(self, settings: Settings) -> None:
        self.url = settings.oscar_url
        self.remote_url = settings.selenium_remote_url
        self.chrome_executable_path = settings.chrome_executable_path
        self.chromedriver_path = settings.chromedriver_path
        self.wait_timeout = settings.selenium_wait_timeout_seconds

    def crawl(self) -> CrawlResult:
        try:
            driver = self._build_driver()
        except WebDriverException as exc:
            raise CrawlerError(f"Failed to start browser session: {exc}") from exc

        try:
            films = self._collect_all_years(driver)
        except (WebDriverException, TimeoutError) as exc:
            raise CrawlerError(f"Failed to crawl oscar page: {exc}") from exc
        finally:
            driver.quit()

        logger.info("oscar_crawl_finished", records=len(films))
        return CrawlResult(oscar=films)

    def _collect_all_years(self, driver: WebDriver) -> list[OscarFilmData]:
        driver.get(self.url)
        wait = WebDriverWait(driver, self.wait_timeout)
        wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "a.year-link")) > 0)

        year_ids = [
            year_id
            for link in driver.find_elements(By.CSS_SELECTOR, "a.year-link")
            if (year_id := link.get_attribute("id"))
        ]
        logger.info("oscar_crawl_started", years=year_ids)

        films: list[OscarFilmData] = []
        for year_id in year_ids:
            films.extend(self._collect_year(driver, wait, year_id))
        return films

    def _collect_year(
        self, driver: WebDriver, wait: WebDriverWait[WebDriver], year_id: str
    ) -> list[OscarFilmData]:
        previous_rows = driver.find_elements(By.CSS_SELECTOR, "tr.film")
        previous_first_row = previous_rows[0] if previous_rows else None

        driver.find_element(By.ID, year_id).click()
        wait.until(lambda d: self._table_ready(d, previous_first_row))

        return parse_films(driver.page_source, int(year_id))

    @staticmethod
    def _table_ready(driver: WebDriver, previous_first_row: WebElement | None) -> bool:
        """Explicit wait condition for a year's table to be fully rendered.

        Three signals are required because the page replaces the table body
        after an artificial delay: the previous year's rows must be stale (a
        row still attached means the old table is on screen), the loading
        spinner must be hidden, and at least one film row must exist.
        """
        if previous_first_row is not None:
            try:
                previous_first_row.is_enabled()
            except StaleElementReferenceException:
                pass
            else:
                return False

        if driver.find_element(By.ID, "loading").is_displayed():
            return False
        return len(driver.find_elements(By.CSS_SELECTOR, "tr.film")) > 0

    def _build_driver(self) -> WebDriver:
        options = ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1280,900")
        if self.chrome_executable_path:
            options.binary_location = self.chrome_executable_path

        if self.remote_url:
            return webdriver.Remote(command_executor=self.remote_url, options=options)

        if self.chromedriver_path:
            service = ChromeService(executable_path=self.chromedriver_path)
            return webdriver.Chrome(service=service, options=options)

        return webdriver.Chrome(options=options)
