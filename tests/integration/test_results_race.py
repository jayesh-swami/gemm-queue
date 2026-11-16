"""Results of one job saved in parallel must still finish the job.

Each consumer (prefetch 10) saves several results at once, and with more than one
replica the results of a job are spread over processes. When the job's status was
stored, two saves of the same job could each miss the other's commit and leave
the job "running" forever, so they had to lock the job row. Now each save writes
only its own run and the status is derived from the runs, so there is nothing
to miss and nothing to lock.
"""

import asyncio
import random

import pytest
from conftest import start_process, stop_process
from helpers import publish_results, wait_until
from sqlalchemy import func, select

from gemm_queue.api.db.models import KernelRunResult
from gemm_queue.api.db.repositories import KernelJobRepository
from gemm_queue.api.db.session import SessionLocal
from gemm_queue.common.enums import RunStatus
from gemm_queue.common.messages import ResultMessage

JOBS = 10


@pytest.fixture
def second_consumer():
    """A second results consumer next to the session one, like RESULTS=2."""
    proc = start_process("gemm_queue.results", "results consumer ready")
    yield
    stop_process(proc)


def test_parallel_results_finish_every_job(second_consumer):
    with SessionLocal() as session:
        repo = KernelJobRepository(session)
        jobs = [repo.add(m=8, n=8, k=8, seed=i) for i in range(JOBS)]
        session.commit()

    results = [
        ResultMessage(
            task_id=run.id,
            job_id=job.id,
            kernel=run.kernel,
            success=True,
            message="",
            ms=1.0,
            tflops=1.0,
            max_error=0.0,
            passed=True,
        )
        for job in jobs
        for run in job.runs
    ]
    random.shuffle(results)
    asyncio.run(publish_results(results))

    def all_runs_saved():
        with SessionLocal() as session:
            done = select(func.count()).where(KernelRunResult.status == RunStatus.DONE)
            return session.scalar(done) == len(results)

    wait_until(all_runs_saved)

    with SessionLocal() as session:
        saved = [KernelJobRepository(session).get(job.id) for job in jobs]
    assert [job.status for job in saved] == [RunStatus.DONE] * JOBS
    assert all(job.finished_at is not None for job in saved)
