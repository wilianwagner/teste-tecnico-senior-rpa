from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import Session, sessionmaker

from app.api.error_handlers import register_error_handlers
from app.api.routes import crawl, health, jobs, results
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import build_engine, build_session_factory
from app.messaging.publisher import CrawlJobPublisher

logger = get_logger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    session_factory: sessionmaker[Session] | None = None,
    publisher: CrawlJobPublisher | None = None,
) -> FastAPI:
    app_settings = settings if settings is not None else get_settings()
    configure_logging(app_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = None
        if session_factory is None:
            engine = build_engine(app_settings)
            app.state.session_factory = build_session_factory(engine)
        else:
            app.state.session_factory = session_factory

        owns_publisher = publisher is None
        if publisher is None:
            app.state.publisher = CrawlJobPublisher(app_settings)
            await app.state.publisher.connect()
        else:
            app.state.publisher = publisher

        logger.info("api_started")
        yield

        if owns_publisher:
            await app.state.publisher.close()
        if engine is not None:
            engine.dispose()
        logger.info("api_stopped")

    app = FastAPI(
        title="RPA Crawler API",
        version="0.1.0",
        description=(
            "Schedules crawl jobs through RabbitMQ, tracks their lifecycle "
            "and serves the collected data."
        ),
        lifespan=lifespan,
    )
    app.state.settings = app_settings

    app.include_router(crawl.router)
    app.include_router(jobs.router)
    app.include_router(results.router)
    app.include_router(health.router)
    register_error_handlers(app)

    return app


app = create_app()
