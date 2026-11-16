"""Chaos tests: break the running stack under load and check that no job is lost.

They run against the dev stack (make up RUNNER=fake WORKERS=4 RESULTS=2), kill and
restart its containers, and add jobs to its database. For the duration of the
run the sweeper is recreated with a 20 s timeout, so recovery takes seconds.
"""

import pytest
from stack import api_ready, compose, containers, podman, queue_depths, start_stopped, wait_until

STUCK_AFTER_S = 20
SWEEP_EVERY_S = 5


def sweeper_timeout() -> float:
    """The timeout the running sweeper actually uses (proves its image has the setting)."""
    out = podman(
        "exec",
        "gemm-queue-sweeper-1",
        "uv",
        "run",
        "--no-sync",
        "python",
        "-c",
        "from gemm_queue.batch.sweeper import STUCK_AFTER; print(STUCK_AFTER.total_seconds())",
    )
    return float(out.splitlines()[-1])


@pytest.fixture(scope="session", autouse=True)
def stack():
    """Up, with fake workers and two of each scaled service, so killing one leaves another."""
    if not api_ready():
        pytest.exit("API not ready; start the stack: make up RUNNER=fake WORKERS=4 RESULTS=2")
    workers, results = containers("worker"), containers("results")
    if len(workers) < 2 or len(results) < 2:
        pytest.exit("needs 2+ workers and 2+ results consumers: make up WORKERS=4 RESULTS=2")
    if (runner := podman("exec", workers[0], "printenv", "WORKER_RUNNER")) != "fake":
        pytest.exit(f"the workers use the {runner} runner; restart them with RUNNER=fake")


@pytest.fixture(scope="session", autouse=True)
def fast_sweeper(stack):
    env = {"SWEEPER_STUCK_AFTER_S": str(STUCK_AFTER_S), "SWEEPER_INTERVAL_S": str(SWEEP_EVERY_S)}
    compose("up", "-d", "sweeper", env=env)
    if sweeper_timeout() != STUCK_AFTER_S:
        pytest.exit("the sweeper image predates SWEEPER_STUCK_AFTER_S; rebuild it: make sweeper")
    yield
    compose("up", "-d", "sweeper")  # back to the defaults


@pytest.fixture(autouse=True)
def recover():
    """Start each test from a quiet system, and bring back whatever it killed."""
    wait_until(
        lambda: queue_depths()["gemm.tasks"] == queue_depths()["gemm.results"] == 0,
        timeout=120,
        what="queues empty before the test",
    )
    yield
    start_stopped()
    wait_until(api_ready, timeout=60, what="API ready after the test")
