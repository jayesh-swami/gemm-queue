"""Integration tests against the Compose Postgres and RabbitMQ (`make db mq`).

Everything runs in its own database and vhost (gemmq_test), so the app's real jobs
and queues are never touched. Tests commit for real: the API, the results consumer
and the worker each use their own connections, so a rolled-back test transaction
would be invisible to them. Tables and queues are emptied before each test instead.
"""

import os

TEST_DB = "gemmq_test"
TEST_VHOST = "gemmq_test"

# Before any gemm_queue import: settings are read once, at import time.
# Users, passwords and the API key still come from the real .env.
os.environ.update(
    {
        "POSTGRES_DB": TEST_DB,
        "POSTGRES_HOST": "localhost",
        "RABBITMQ_VHOST": TEST_VHOST,
        "RABBITMQ_HOST": "localhost",
    }
)

import asyncio  # noqa: E402
import base64  # noqa: E402
import json  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import threading  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402
from urllib.parse import quote  # noqa: E402

import psycopg  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from helpers import purge, wait_until  # noqa: E402
from sqlalchemy import text  # noqa: E402

from gemm_queue import mq  # noqa: E402
from gemm_queue.config import ROOT, settings  # noqa: E402
from gemm_queue.db.session import dbEngine  # noqa: E402

QUEUES = (mq.TASKS_QUEUE, mq.TASKS_DLQ, mq.RESULTS_QUEUE, mq.RESULTS_DLQ)


def alembic_config() -> Config:
    return Config(ROOT / "alembic.ini")


def rabbit_api(method: str, path: str, body: dict | None = None) -> None:
    """Call the RabbitMQ management API (published on localhost:15672)."""
    request = urllib.request.Request(
        f"http://{settings.rabbitmq_host}:15672/api/{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"content-type": "application/json"},
    )
    auth = f"{settings.rabbitmq_user}:{settings.rabbitmq_password}".encode()
    request.add_header("Authorization", "Basic " + base64.b64encode(auth).decode())
    urllib.request.urlopen(request, timeout=5).close()


def recreate_database() -> None:
    with psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password,
        dbname="postgres",
        autocommit=True,
        connect_timeout=3,
    ) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {TEST_DB}")


def recreate_vhost() -> None:
    try:
        rabbit_api("DELETE", f"vhosts/{TEST_VHOST}")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    rabbit_api("PUT", f"vhosts/{TEST_VHOST}")
    rabbit_api(
        "PUT",
        f"permissions/{TEST_VHOST}/{quote(settings.rabbitmq_user, safe='')}",
        {"configure": ".*", "write": ".*", "read": ".*"},
    )


@pytest.fixture(scope="session", autouse=True)
def services():
    """Fresh test DB (migrated) and vhost. Stops the whole run if a service is down."""
    try:
        recreate_database()
    except psycopg.OperationalError as exc:
        pytest.exit(f"Postgres not reachable, start it with `make db`: {exc}", returncode=1)
    try:
        recreate_vhost()
    except OSError as exc:
        pytest.exit(f"RabbitMQ not reachable, start it with `make mq`: {exc}", returncode=1)
    command.upgrade(alembic_config(), "head")


@pytest.fixture(scope="session", autouse=True)
def worker(services):
    """The real worker process, with the fake runner."""
    env = {**os.environ, "WORKER_RUNNER": "fake", "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "gemm_queue.worker"],
        cwd=ROOT,
        env=env,
        stderr=subprocess.PIPE,
        text=True,
    )
    # Keep reading its log, so the pipe never fills up and blocks it.
    lines: list[str] = []
    threading.Thread(target=lambda: lines.extend(proc.stderr), daemon=True).start()
    try:
        wait_until(lambda: any("worker ready" in line for line in lines), timeout=30)
    except AssertionError:
        proc.kill()
        pytest.exit("worker didn't start:\n" + "".join(lines), returncode=1)
    yield proc
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="session", autouse=True)
def client(services):
    """The API with its lifespan running, so the results consumer is live."""
    from gemm_queue.api.main import app

    with TestClient(app, headers={"X-API-Key": settings.api_key}) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean(client, worker):
    with dbEngine.begin() as conn:
        conn.execute(text("TRUNCATE jobs, results RESTART IDENTITY CASCADE"))
    asyncio.run(purge(*QUEUES))
