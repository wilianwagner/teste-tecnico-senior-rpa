from app.core.config import Settings
from app.core.enums import JobSource
from app.crawlers.base import Crawler
from app.crawlers.hockey.crawler import HockeyCrawler
from app.crawlers.oscar.crawler import OscarCrawler

CrawlerRegistry = dict[JobSource, tuple[Crawler, ...]]


def build_crawler_registry(settings: Settings) -> CrawlerRegistry:
    hockey = HockeyCrawler(settings)
    oscar = OscarCrawler(settings)
    return {
        JobSource.HOCKEY: (hockey,),
        JobSource.OSCAR: (oscar,),
        JobSource.ALL: (hockey, oscar),
    }
