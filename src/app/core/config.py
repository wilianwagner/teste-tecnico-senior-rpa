from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://rpa:rpa@localhost:5432/rpa"
    rabbitmq_url: str = "amqp://rpa:rpa@localhost:5672/"

    crawl_exchange: str = "crawler"
    crawl_queue: str = "crawl_jobs"
    crawl_routing_key: str = "crawl"
    crawl_dlx: str = "crawler.dlx"
    crawl_dlq: str = "crawl_jobs.dlq"
    crawl_max_attempts: int = 3

    selenium_remote_url: str = ""
    chrome_executable_path: str = ""
    chromedriver_path: str = ""

    hockey_base_url: str = "https://www.scrapethissite.com/pages/forms/"
    hockey_per_page: int = 100
    oscar_url: str = "https://www.scrapethissite.com/pages/ajax-javascript/"

    http_timeout_seconds: float = 15.0
    selenium_wait_timeout_seconds: float = 30.0

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
