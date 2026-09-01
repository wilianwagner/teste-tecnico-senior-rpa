from fastapi.testclient import TestClient


class TestDashboard:
    def test_root_serves_dashboard_page(self, client: TestClient) -> None:
        response = client.get("/")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "RPA Crawler" in response.text

    def test_dashboard_is_not_in_openapi_schema(self, client: TestClient) -> None:
        assert "/" not in client.get("/openapi.json").json()["paths"]
