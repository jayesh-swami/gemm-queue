"""Results of one job saved in parallel must still finish the job.

The consumer (prefetch 10) saves several results at once. Without the job-row lock
(get_for_update), two saves of the same job can each miss the other's commit,
both see an unfinished run, and the job stays "running" forever.
"""

import asyncio
import random

from helpers import publish_results, wait_until
from sqlalchemy import func, select

from gemm_queue.api.db.models import KernelJob, KernelRunResult
from gemm_queue.api.db.repositories import KernelJobRepository
from gemm_queue.api.db.session import SessionLocal
from gemm_queue.common.enums import RunStatus
from gemm_queue.common.messages import ResultMessage

JOBS = 10


def test_parallel_results_finish_every_job():
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
        statuses = session.scalars(select(KernelJob.status)).all()
    assert statuses == [RunStatus.DONE] * JOBS
