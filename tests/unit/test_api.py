import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.enums import JobSource
from app.core.exceptions import PublishError
from app.db.repositories.jobs import JobRepository
from app.db.repositories.results import ResultRepository
from app.main import create_app
from app.messaging.messages import CrawlJobMessage
from app.schemas.crawl import HockeyTeamData, OscarFilmData

HOCKEY_ROW = HockeyTeamData(
    team_name="Boston Bruins",
    year=1990,
    wins=44,
    losses=24,
    ot_losses=None,
    win_pct=0.55,
    goals_for=299,
    goals_against=264,
    goal_diff=35,
)

OSCAR_ROW = OscarFilmData(year=2015, title="Spotlight", nominations=6, awards=2, best_picture=True)


class FakePublisher:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.published: list[CrawlJobMessage] = []

    async def publish(self, message: CrawlJobMessage) -> None:
        if self.error is not None:
            raise self.error
        self.published.append(message)

    async def ping(self) -> bool:
        return True


def make_client(session_factory: sessionmaker[Session], publisher: FakePublisher) -> TestClient:
    app = create_app(
        Settings(),
        session_factory=session_factory,
        publisher=publisher,  # type: ignore[arg-type]
    )
    return TestClient(app)


@pytest.fixture
def publisher() -> FakePublisher:
    return FakePublisher()


@pytest.fixture
def client(
    session_factory: sessionmaker[Session], publisher: FakePublisher
) -> Iterator[TestClient]:
    with make_client(session_factory, publisher) as test_client:
        yield test_client


def complete_job_with_results(
    session_factory: sessionmaker[Session],
    job_id: str,
    *,
    hockey: list[HockeyTeamData] | None = None,
    oscar: list[OscarFilmData] | None = None,
) -> None:
    with session_factory() as session:
        jobs = JobRepository(session)
        results = ResultRepository(session)
        job = jobs.get(uuid.UUID(job_id))
        assert job is not None
        records = 0
        if hockey:
            records += results.replace_hockey(job.id, hockey)
        if oscar:
            records += results.replace_oscar(job.id, oscar)
        jobs.mark_running(job)
        jobs.mark_completed(job, records)
        session.commit()


class TestScheduleCrawl:
    @pytest.mark.parametrize("source", ["hockey", "oscar", "all"])
    def test_returns_202_with_job_id(
        self, client: TestClient, publisher: FakePublisher, source: str
    ) -> None:
        response = client.post(f"/crawl/{source}")

        assert response.status_code == 202
        body = response.json()
        assert body["source"] == source
        assert body["status"] == "pending"
        assert uuid.UUID(body["job_id"])
        assert publisher.published[-1].source == JobSource(source)

    def test_unknown_source_returns_422(self, client: TestClient) -> None:
        assert client.post("/crawl/banana").status_code == 422

    def test_publish_failure_returns_503_and_marks_job_failed(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        failing_publisher = FakePublisher(error=PublishError("broker down"))
        with make_client(session_factory, failing_publisher) as client:
            response = client.post("/crawl/hockey")

            assert response.status_code == 503
            jobs = client.get("/jobs").json()
            assert jobs["total"] == 1
            assert jobs["items"][0]["status"] == "failed"


class TestJobs:
    def test_list_jobs_with_filters_and_pagination(self, client: TestClient) -> None:
        client.post("/crawl/hockey")
        client.post("/crawl/oscar")
        client.post("/crawl/oscar")

        all_jobs = client.get("/jobs").json()
        assert all_jobs["total"] == 3

        oscar_jobs = client.get("/jobs", params={"source": "oscar"}).json()
        assert oscar_jobs["total"] == 2

        paged = client.get("/jobs", params={"limit": 1, "offset": 0}).json()
        assert paged["total"] == 3
        assert len(paged["items"]) == 1

    def test_get_job_detail(self, client: TestClient) -> None:
        job_id = client.post("/crawl/hockey").json()["job_id"]

        response = client.get(f"/jobs/{job_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == job_id
        assert body["status"] == "pending"
        assert body["attempts"] == 0

    def test_get_unknown_job_returns_404(self, client: TestClient) -> None:
        response = client.get(f"/jobs/{uuid.uuid4()}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


class TestJobResults:
    def test_pending_job_has_empty_results(self, client: TestClient) -> None:
        job_id = client.post("/crawl/hockey").json()["job_id"]

        body = client.get(f"/jobs/{job_id}/results").json()

        assert body["status"] == "pending"
        assert body["hockey"]["items"] == []
        assert "oscar" not in body

    def test_completed_job_returns_collected_rows(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        job_id = client.post("/crawl/all").json()["job_id"]
        complete_job_with_results(session_factory, job_id, hockey=[HOCKEY_ROW], oscar=[OSCAR_ROW])

        body = client.get(f"/jobs/{job_id}/results").json()

        assert body["status"] == "completed"
        assert body["records_collected"] == 2
        assert body["hockey"]["items"][0]["team_name"] == "Boston Bruins"
        assert body["oscar"]["items"][0]["title"] == "Spotlight"
        assert body["oscar"]["items"][0]["best_picture"] is True


class TestResultSnapshots:
    def test_empty_snapshot_when_no_completed_job(self, client: TestClient) -> None:
        body = client.get("/results/hockey").json()

        assert body["job_id"] is None
        assert body["items"] == []
        assert body["total"] == 0

    def test_returns_data_from_latest_completed_job(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        first_id = client.post("/crawl/hockey").json()["job_id"]
        complete_job_with_results(session_factory, first_id, hockey=[HOCKEY_ROW])

        newer_row = HOCKEY_ROW.model_copy(update={"team_name": "Chicago Blackhawks"})
        second_id = client.post("/crawl/hockey").json()["job_id"]
        complete_job_with_results(session_factory, second_id, hockey=[newer_row])

        body = client.get("/results/hockey").json()

        assert body["job_id"] == second_id
        assert [item["team_name"] for item in body["items"]] == ["Chicago Blackhawks"]

    def test_snapshot_filters(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        job_id = client.post("/crawl/oscar").json()["job_id"]
        other = OSCAR_ROW.model_copy(update={"title": "Mad Max: Fury Road", "year": 2015})
        older = OSCAR_ROW.model_copy(update={"title": "Argo", "year": 2012})
        complete_job_with_results(session_factory, job_id, oscar=[OSCAR_ROW, other, older])

        by_year = client.get("/results/oscar", params={"year": 2012}).json()
        assert [item["title"] for item in by_year["items"]] == ["Argo"]

        by_title = client.get("/results/oscar", params={"title": "spot"}).json()
        assert [item["title"] for item in by_title["items"]] == ["Spotlight"]


class TestHealth:
    def test_healthy_service_returns_ok(self, client: TestClient) -> None:
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": True, "broker": True}
