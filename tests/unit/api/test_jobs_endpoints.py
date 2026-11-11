"""The /jobs endpoints, with SQLite for the DB and a fake RabbitMQ channel.

TestClient is used without `with`, so the app's lifespan (the real RabbitMQ
connection) never runs.
"""

import aio_pika
import pytest
from conftest import API_KEY
from fastapi.testclient import TestClient

from gemm_queue.api.dependencies import get_db_session, get_mq_channel
from gemm_queue.api.main import app
from gemm_queue.common import mq
from gemm_queue.common.enums import Kernel
from gemm_queue.common.messages import TaskMessage


class FakeExchange:
    def __init__(self) -> None:
        self.published: list[tuple[str, aio_pika.Message]] = []
        self.down = False

    async def publish(self, message, routing_key, timeout=None):
        if self.down:
            raise ConnectionError("broker down")
        self.published.append((routing_key, message))


class FakeChannel:
    def __init__(self) -> None:
        self.default_exchange = FakeExchange()


@pytest.fixture
def exchange():
    return FakeExchange()


@pytest.fixture
def client(session_factory, exchange):
    channel = FakeChannel()
    channel.default_exchange = exchange

    def db_session():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = db_session
    app.dependency_overrides[get_mq_channel] = lambda: channel
    yield TestClient(app, headers={"X-API-Key": API_KEY})
    app.dependency_overrides.clear()


def post_job(client, **body):
    return client.post("/jobs", json={"m": 64, "n": 32, "k": 16, **body})


# --- POST /jobs ---


def test_create_returns_id_and_the_given_seed(client):
    res = post_job(client, seed=123)
    assert res.status_code == 202
    assert res.json() == {"job_id": 1, "seed": 123}


def test_create_picks_a_seed_when_none_is_given(client):
    seed = post_job(client).json()["seed"]
    assert 0 <= seed < 2**31


def test_create_publishes_one_persistent_task_per_kernel(client, exchange):
    job = post_job(client, seed=7).json()

    assert [queue for queue, _ in exchange.published] == [mq.TASKS_QUEUE] * len(Kernel)
    tasks = [TaskMessage.model_validate_json(msg.body) for _, msg in exchange.published]
    assert {t.kernel for t in tasks} == set(Kernel)
    for task, (_, msg) in zip(tasks, exchange.published, strict=True):
        assert (task.job_id, task.m, task.n, task.k, task.seed) == (job["job_id"], 64, 32, 16, 7)
        assert msg.message_id == str(task.task_id)
        assert msg.delivery_mode == aio_pika.DeliveryMode.PERSISTENT


def test_broker_down_still_saves_the_job(client, exchange):
    exchange.down = True
    res = post_job(client)

    assert res.status_code == 202
    assert client.get(f"/jobs/{res.json()['job_id']}").json()["status"] == "queued"


def test_invalid_request_publishes_nothing(client, exchange):
    assert post_job(client, m=0).status_code == 422
    assert exchange.published == []


# --- auth ---


@pytest.mark.parametrize("headers", [{"X-API-Key": "wrong"}, {}])
def test_requests_without_the_right_key_are_rejected(client, headers):
    client.headers.clear()
    assert client.post("/jobs", json={"m": 1, "n": 1, "k": 1}, headers=headers).status_code == 401
    assert client.get("/jobs", headers=headers).status_code == 401


# --- GET /jobs/{id} and GET /jobs ---


def test_get_job_returns_its_runs_in_kernel_order(client):
    job_id = post_job(client).json()["job_id"]
    job = client.get(f"/jobs/{job_id}").json()

    assert job["job_id"] == job_id
    assert job["status"] == "queued"
    assert [r["kernel"] for r in job["kernel_runs"]] == [k.value for k in Kernel]


def test_get_missing_job_is_404(client):
    assert client.get("/jobs/999").status_code == 404


def test_list_is_newest_first_and_respects_limit(client):
    ids = [post_job(client).json()["job_id"] for _ in range(3)]

    assert [j["job_id"] for j in client.get("/jobs").json()] == ids[::-1]
    assert [j["job_id"] for j in client.get("/jobs?limit=2").json()] == ids[:0:-1]
    assert client.get("/jobs?limit=101").status_code == 422
