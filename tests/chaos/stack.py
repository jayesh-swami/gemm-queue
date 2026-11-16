"""Drives the running compose stack for the chaos tests: containers, load, checks."""

import base64
import json
import os
import subprocess
import threading
import time
import urllib.request
from collections.abc import Callable
from datetime import datetime
from typing import Self

from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from gemm_queue.api.db.models import KernelJob, KernelRunResult
from gemm_queue.api.settings import settings
from gemm_queue.common.enums import RunStatus
from gemm_queue.common.settings import ROOT

API = "http://localhost:8000"
MANAGEMENT = "http://localhost:15672/api"
COMPOSE = ["podman", "compose", "-f", "deploy/docker-compose.yml", "--project-directory", "."]
PROJECT = "gemm-queue"

# Our own engine: pre_ping drops connections that died with a Postgres restart.
engine = create_engine(settings.database_url, pool_pre_ping=True)


def podman(*args: str) -> str:
    return subprocess.run(
        ["podman", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def compose(*args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(
        COMPOSE + list(args),
        cwd=ROOT,
        env={**os.environ, **(env or {})},
        capture_output=True,
        check=True,
    )


def containers(service: str) -> list[str]:
    """Running containers of a compose service, e.g. gemm-queue-worker-1."""
    names = podman("ps", "--filter", f"name=^{PROJECT}-{service}-[0-9]+$", "--format", "{{.Names}}")
    return sorted(names.split())


def start_stopped() -> None:
    """Start every container of the project that a test killed or stopped."""
    exited = podman(
        "ps",
        "-a",
        "--filter",
        f"label=com.docker.compose.project={PROJECT}",
        "--filter",
        "status=exited",
        "--format",
        "{{.Names}}",
    ).split()
    for name in exited:
        podman("start", name)


def api_ready() -> bool:
    try:
        urllib.request.urlopen(f"{API}/ready", timeout=5).close()
        return True
    except OSError:
        return False


def management(method: str, path: str):
    request = urllib.request.Request(f"{MANAGEMENT}/{path}", method=method)
    auth = f"{settings.rabbitmq_user}:{settings.rabbitmq_password}".encode()
    request.add_header("Authorization", "Basic " + base64.b64encode(auth).decode())
    with urllib.request.urlopen(request, timeout=5) as response:
        body = response.read()
        return json.loads(body) if body else None


def queue_depths() -> dict[str, int]:
    """Messages per queue. RabbitMQ refreshes these every few seconds."""
    queues = management("GET", "queues/%2F?columns=name,messages")
    return {q["name"]: q.get("messages", 0) for q in queues}


def purge(queue: str) -> None:
    management("DELETE", f"queues/%2F/{queue}/contents")


def wait_until[T](predicate: Callable[[], T], timeout: float, what: str) -> T:
    deadline = time.monotonic() + timeout
    while True:
        try:
            value = predicate()
        except OSError, SQLAlchemyError:
            value = None  # a service is still coming back up
        if value:
            return value
        if time.monotonic() > deadline:
            raise AssertionError(f"{what} not true within {timeout:.0f} s")
        time.sleep(1)


def db_now() -> datetime:
    with Session(engine) as session:
        return session.scalar(select(func.now()))


class Load:
    """Submits small jobs from a few threads until stopped.

    `accepted` holds every job the API answered 202 for: the jobs the system
    promised to finish. Any other answer, or no answer, counts as a failure the
    client saw, which is allowed while a service is down.
    """

    def __init__(self, threads: int = 4, every: float = 0.1) -> None:
        self.accepted: list[int] = []
        self.failures = 0
        self._every = every
        self._stop = threading.Event()
        self._threads = [threading.Thread(target=self._run, daemon=True) for _ in range(threads)]

    def __enter__(self) -> Self:
        for thread in self._threads:
            thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join()

    def _run(self) -> None:
        while not self._stop.is_set():
            request = urllib.request.Request(
                f"{API}/jobs",
                data=json.dumps({"m": 64, "n": 64, "k": 64}).encode(),
                headers={"Content-Type": "application/json", "X-API-Key": settings.api_key},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    self.accepted.append(json.load(response)["job_id"])
            except OSError, ValueError:  # HTTP errors, refused, timeouts, bad JSON
                self.failures += 1
            time.sleep(self._every)


def jobs_since(start: datetime) -> dict[int, RunStatus]:
    """Every job created since start, accepted or not, with its status."""
    with Session(engine) as session:
        rows = session.execute(
            select(KernelJob.id, KernelJob.status).where(KernelJob.created_at >= start)
        )
        return {job_id: status for job_id, status in rows}


def runs_of(job_ids: list[int]) -> list[KernelRunResult]:
    with Session(engine) as session:
        return list(
            session.scalars(select(KernelRunResult).where(KernelRunResult.job_id.in_(job_ids)))
        )
