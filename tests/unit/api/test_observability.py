"""/health, /ready and /metrics. TestClient without `with`: no lifespan, so no RabbitMQ."""

import pytest
from fastapi.testclient import TestClient

from gemm_queue.api.dependencies import get_db_session
from gemm_queue.api.main import app


@pytest.fixture
def client(session_factory):
    def db_session():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health(client):
    assert client.get("/health").status_code == 200


def test_not_ready_without_rabbitmq(client):
    res = client.get("/ready")
    assert res.status_code == 503
    assert res.json()["detail"] == "RabbitMQ unreachable"


def test_metrics_count_requests_by_route_template(client):
    client.get("/health")
    client.get("/jobs/12345", headers={"X-API-Key": "wrong"})

    body = client.get("/metrics").text
    assert 'api_http_requests_total{method="GET",route="/health",status="200"}' in body
    # the template, not /jobs/12345, so each job id doesn't become its own series
    assert 'route="/jobs/{job_id}",status="401"' in body
