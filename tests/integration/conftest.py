import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.session import build_engine, build_session_factory

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
    except Exception:
        return False
    return True


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _docker_available():
        return
    skip_marker = pytest.mark.skip(
        reason="Docker is not available; integration tests require Testcontainers"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="psycopg") as container:
        yield container.get_connection_url()


@pytest.fixture(scope="session")
def rabbitmq_url() -> Iterator[str]:
    from testcontainers.core.container import DockerContainer

    container = (
        DockerContainer("rabbitmq:4-alpine")
        .with_env("RABBITMQ_DEFAULT_USER", "test")
        .with_env("RABBITMQ_DEFAULT_PASS", "test")
        .with_exposed_ports(5672)
    )
    with container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(5672)
        url = f"amqp://test:test@{host}:{port}/"
        _wait_for_amqp(url)
        yield url


def _wait_for_amqp(url: str, timeout: float = 60.0) -> None:
    import time

    import pika
    import pika.exceptions

    deadline = time.monotonic() + timeout
    while True:
        try:
            pika.BlockingConnection(pika.URLParameters(url)).close()
        except pika.exceptions.AMQPConnectionError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)
        else:
            return


@pytest.fixture(scope="session")
def migrated_engine(postgres_url: str) -> Iterator[Engine]:
    alembic_config = Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", postgres_url)
    command.upgrade(alembic_config, "head")

    engine = build_engine(Settings(database_url=postgres_url))
    yield engine
    engine.dispose()


@pytest.fixture
def db_session_factory(migrated_engine: Engine) -> sessionmaker[Session]:
    return build_session_factory(migrated_engine)


@pytest.fixture(autouse=True)
def _clean_tables(migrated_engine: Engine) -> Iterator[None]:
    yield
    with migrated_engine.begin() as connection:
        connection.execute(text("TRUNCATE oscar_films, hockey_team_stats, jobs CASCADE"))


@pytest.fixture
def integration_settings(postgres_url: str, rabbitmq_url: str) -> Settings:
    suffix = uuid.uuid4().hex[:8]
    return Settings(
        database_url=postgres_url,
        rabbitmq_url=rabbitmq_url,
        crawl_exchange=f"crawler-{suffix}",
        crawl_queue=f"crawl-jobs-{suffix}",
        crawl_dlx=f"crawler-dlx-{suffix}",
        crawl_dlq=f"crawl-jobs-dlq-{suffix}",
        crawl_max_attempts=2,
    )
