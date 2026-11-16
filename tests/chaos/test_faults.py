"""One fault per test, injected mid-load. Afterwards the same guarantees must hold:

- every job the API accepted (202) is in the database and finishes;
- every run of those jobs has a result (with the fake runner, all of them pass);
- nothing is left in a dead-letter queue.

Jobs whose POST failed while a service was down are not promised to anyone, but
any that did get saved must finish too, so the checks cover every job created
during the test.
"""

import time
from collections.abc import Callable
from datetime import datetime

from stack import (
    Load,
    containers,
    db_now,
    jobs_since,
    podman,
    purge,
    queue_depths,
    runs_of,
    wait_until,
)

from gemm_queue.api.db.models import KernelRunResult
from gemm_queue.common.enums import RunStatus

DLQS = ("gemm.tasks.dlq", "gemm.results.dlq")
FINISHED = {RunStatus.DONE, RunStatus.FAILED}
# 20 s sweeper timeout, a few 5 s passes, and time to drain.
SETTLE_S = 120


def under_load(fault: Callable[[], None], before_s: float = 5, after_s: float = 15):
    """Run the load, inject the fault partway through, keep the load going after it."""
    start = db_now()
    dlqs_before = {q: queue_depths()[q] for q in DLQS}
    with Load() as load:
        time.sleep(before_s)
        fault()
        time.sleep(after_s)
    return load, start, dlqs_before


def assert_nothing_lost(
    load: Load, start: datetime, dlqs_before: dict[str, int]
) -> list[KernelRunResult]:
    assert load.accepted, "the API accepted no jobs, so the test proves nothing"

    def all_finished():
        jobs = jobs_since(start)
        return jobs if jobs and all(s in FINISHED for s in jobs.values()) else None

    jobs = wait_until(all_finished, timeout=SETTLE_S, what="every job finished")

    missing = set(load.accepted) - jobs.keys()
    assert not missing, f"{len(missing)} accepted jobs are not in the database"

    runs = runs_of(list(jobs))
    assert len(runs) == 5 * len(jobs)
    not_done = [r.id for r in runs if r.status != RunStatus.DONE]
    assert not not_done, f"{len(not_done)} runs did not complete: {not_done[:10]}"

    time.sleep(6)  # queue counts refresh every few seconds
    assert {q: queue_depths()[q] for q in DLQS} == dlqs_before, "messages were dead-lettered"

    republished = sum(r.attempts > 1 for r in runs)
    print(
        f"\n  {len(load.accepted)} jobs accepted, {load.failures} requests failed, "
        f"{len(jobs)} jobs finished, {republished} runs re-published by the sweeper"
    )
    return runs


def test_worker_killed_mid_task():
    """Its unacked task goes back to the queue when its connection drops."""
    worker = containers("worker")[0]
    load, start, dlqs = under_load(lambda: podman("kill", worker))

    runs = assert_nothing_lost(load, start, dlqs)
    assert all(r.attempts == 1 for r in runs), "recovered by redelivery, not the sweeper"


def test_results_consumer_killed_mid_save():
    """Its unacked results are redelivered to the other consumer; saves are idempotent."""
    consumer = containers("results")[0]
    load, start, dlqs = under_load(lambda: podman("kill", consumer))

    runs = assert_nothing_lost(load, start, dlqs)
    assert all(r.attempts == 1 for r in runs), "recovered by redelivery, not the sweeper"


def test_rabbitmq_restarts():
    """Queues are durable and clients reconnect. Tasks whose publish failed during the
    restart stay queued in Postgres, and the sweeper re-publishes them."""
    load, start, dlqs = under_load(lambda: podman("restart", "gemm-queue-mq-1"), after_s=25)

    assert_nothing_lost(load, start, dlqs)


def test_postgres_restarts():
    """POSTs fail while it's down (the client sees that); results wait and are retried."""
    load, start, dlqs = under_load(lambda: podman("restart", "gemm-queue-db-1"), after_s=25)

    assert_nothing_lost(load, start, dlqs)


def test_queued_tasks_lost():
    """Tasks vanish from the queue (here: a purge). Only the sweeper can bring them back."""

    def lose_tasks():
        workers = containers("worker")
        podman("stop", *workers)  # let tasks pile up, so the purge has something to remove
        time.sleep(3)
        purge("gemm.tasks")
        podman("start", *workers)

    load, start, dlqs = under_load(lose_tasks)

    runs = assert_nothing_lost(load, start, dlqs)
    assert any(r.attempts > 1 for r in runs), "the sweeper should have re-published some"
