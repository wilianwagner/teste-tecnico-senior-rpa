import signal
from types import FrameType

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.crawlers.registry import build_crawler_registry
from app.db.session import build_engine, build_session_factory
from app.worker.consumer import CrawlConsumer
from app.worker.processor import JobProcessor

logger = get_logger(__name__)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    registry = build_crawler_registry(settings)
    processor = JobProcessor(session_factory, registry, settings.crawl_max_attempts)
    consumer = CrawlConsumer(settings, processor)

    def handle_shutdown(signum: int, frame: FrameType | None) -> None:
        logger.info("shutdown_requested", signal=signal.Signals(signum).name)
        consumer.request_stop()

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    logger.info("worker_starting")
    consumer.run()
    engine.dispose()


if __name__ == "__main__":
    main()
