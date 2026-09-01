import threading
import time
from collections.abc import Iterator
from typing import Any

import pika
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.core.config import Settings
from app.core.enums import JobSource
from app.core.exceptions import CrawlerError
from app.crawlers.base import CrawlResult
from app.db.session import build_session_factory
from app.main import create_app
from app.schemas.crawl import HockeyTeamData
from app.worker.consumer import CrawlConsumer
from app.worker.processor import JobProcessor
from tests.integration.test_queue import basic_get_with_retry
from tests.unit.helpers import StubCrawler

pytestmark = pytest.mark.integration

HOCKEY_ROWS = [
    HockeyTeamData(
        team_name="Boston Bruins",
        year=1990,
        wins=44,
        losses=24,
        ot_losses=None,
        win_pct=0.55,
        goals_for=299,
        goals_against=264,
        goal_diff=35,
    ),
    HockeyTeamData(
        team_name="Buffalo Sabres",
        year=1990,
        wins=31,
        losses=30,
        ot_losses=None,
        win_pct=0.388,
        goals_for=292,
        goals_against=278,
        goal_diff=14,
    ),
]


class WorkerHarness:
    def __init__(
        self, settings: Settings, engine: Engine, registry: dict[JobSource, tuple[Any, ...]]
    ) -> None:
        processor = JobProcessor(
            build_session_factory(engine), registry, settings.crawl_max_attempts
        )
        self.consumer = CrawlConsumer(settings, processor)
        self.thread = threading.Thread(target=self.consumer.run, daemon=True)

    def __enter__(self) -> "WorkerHarness":
        self.thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.consumer.request_stop()
        self.thread.join(timeout=10)


@pytest.fixture
def api_client(integration_settings: Settings) -> Iterator[TestClient]:
    app = create_app(integration_settings)
    with TestClient(app) as client:
        yield client


def wait_for_job_status(
    client: TestClient, job_id: str, expected: set[str], timeout: float = 20.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    body: dict[str, Any] = {}
    while time.monotonic() < deadline:
        body = client.get(f"/jobs/{job_id}").json()
        if body.get("status") in expected:
            return body
        time.sleep(0.2)
    raise AssertionError(f"Job {job_id} did not reach {expected} in time, last state: {body}")


def test_full_flow_from_schedule_to_results(
    integration_settings: Settings, migrated_engine: Engine, api_client: TestClient
) -> None:
    crawler = StubCrawler(JobSource.HOCKEY, CrawlResult(hockey=HOCKEY_ROWS))
    registry: dict[JobSource, tuple[Any, ...]] = {JobSource.HOCKEY: (crawler,)}

    with WorkerHarness(integration_settings, migrated_engine, registry):
        response = api_client.post("/crawl/hockey")
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        job = wait_for_job_status(api_client, job_id, {"completed"})
        assert job["records_collected"] == 2
        assert job["attempts"] == 1

        results = api_client.get(f"/jobs/{job_id}/results").json()
        assert results["status"] == "completed"
        names = {item["team_name"] for item in results["hockey"]["items"]}
        assert names == {"Boston Bruins", "Buffalo Sabres"}

        snapshot = api_client.get("/results/hockey").json()
        assert snapshot["job_id"] == job_id
        assert snapshot["total"] == 2

    assert crawler.calls == 1


def test_failing_job_retries_until_dead_letter(
    integration_settings: Settings, migrated_engine: Engine, api_client: TestClient
) -> None:
    crawler = StubCrawler(JobSource.OSCAR, error=CrawlerError("target site unavailable"))
    registry: dict[JobSource, tuple[Any, ...]] = {JobSource.OSCAR: (crawler,)}

    with WorkerHarness(integration_settings, migrated_engine, registry):
        job_id = api_client.post("/crawl/oscar").json()["job_id"]

        job = wait_for_job_status(api_client, job_id, {"failed"})
        assert job["attempts"] == integration_settings.crawl_max_attempts
        assert "target site unavailable" in job["error_message"]

    assert crawler.calls == integration_settings.crawl_max_attempts

    connection = pika.BlockingConnection(pika.URLParameters(integration_settings.rabbitmq_url))
    try:
        channel = connection.channel()
        _, _, dead_body = basic_get_with_retry(channel, integration_settings.crawl_dlq)
        assert job_id in dead_body.decode()
    finally:
        connection.close()


def test_all_source_persists_both_datasets(
    integration_settings: Settings, migrated_engine: Engine, api_client: TestClient
) -> None:
    from app.schemas.crawl import OscarFilmData

    oscar_rows = [
        OscarFilmData(year=2015, title="Spotlight", nominations=6, awards=2, best_picture=True)
    ]
    registry: dict[JobSource, tuple[Any, ...]] = {
        JobSource.ALL: (
            StubCrawler(JobSource.HOCKEY, CrawlResult(hockey=HOCKEY_ROWS)),
            StubCrawler(JobSource.OSCAR, CrawlResult(oscar=oscar_rows)),
        )
    }

    with WorkerHarness(integration_settings, migrated_engine, registry):
        job_id = api_client.post("/crawl/all").json()["job_id"]
        job = wait_for_job_status(api_client, job_id, {"completed"})
        assert job["records_collected"] == 3

        results = api_client.get(f"/jobs/{job_id}/results").json()
        assert len(results["hockey"]["items"]) == 2
        assert len(results["oscar"]["items"]) == 1
        assert results["oscar"]["items"][0]["best_picture"] is True
