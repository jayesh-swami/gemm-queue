"""Re-publishes runs whose result never arrived; fails them after MAX_ATTEMPTS.

Run with `python -m gemm_queue.batch.sweeper`. Covers tasks that were never
published, landed in a DLQ, or got lost, so every job eventually finishes.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from aio_pika.abc import AbstractChannel
from sqlalchemy import select

from gemm_queue.api.db.models import KernelRunResult
from gemm_queue.api.db.repositories import KernelJobRepository, SweeperRunRepository
from gemm_queue.api.db.session import SessionLocal
from gemm_queue.api.settings import settings
from gemm_queue.batch.metrics import FAILED, LAST_SUCCESS, REGISTRY, REPUBLISHED
from gemm_queue.common import mq
from gemm_queue.common.enums import RunStatus
from gemm_queue.common.messages import TaskMessage
from gemm_queue.common.metrics import push

logger = logging.getLogger(__name__)

# A queued run untouched for this long is treated as lost.
STUCK_AFTER = timedelta(minutes=10)
MAX_ATTEMPTS = 3
INTERVAL_S = 60


async def sweep_once(channel: AbstractChannel) -> tuple[int, int]:
    """One pass. Returns (re-published, failed).

    The DB calls are sync and block the loop briefly; nothing else runs here.
    """
    cutoff = datetime.now(UTC) - STUCK_AFTER
    with SessionLocal() as session:
        job_ids = session.scalars(
            select(KernelRunResult.job_id)
            .where(KernelRunResult.status == RunStatus.QUEUED, KernelRunResult.updated_at < cutoff)
            .distinct()
        ).all()

    republished = failed = 0
    for job_id in job_ids:
        with SessionLocal() as session:
            # Job row first, then its runs: the same lock order as the results consumer.
            job = KernelJobRepository(session).get_for_update(job_id)
            for run in job.runs:
                if run.status != RunStatus.QUEUED or run.updated_at >= cutoff:
                    continue  # finished, or retried by another pass meanwhile
                if run.attempts >= MAX_ATTEMPTS:
                    run.status = RunStatus.FAILED
                    run.error = f"no result after {MAX_ATTEMPTS} attempts"
                    failed += 1
                else:
                    task = TaskMessage(
                        task_id=run.id,
                        job_id=job.id,
                        kernel=run.kernel,
                        m=job.m,
                        n=job.n,
                        k=job.k,
                        seed=job.seed,
                    )
                    await mq.publish_task(channel, task)
                    run.attempts += 1  # also bumps updated_at, restarting the timeout
                    republished += 1
            job.refresh_status()
            session.commit()
    return republished, failed


async def run_pass(channel: AbstractChannel) -> tuple[int, int]:
    """sweep_once, then log the pass in sweeper_runs and push the metrics."""
    republished, failed = await sweep_once(channel)
    with SessionLocal() as session:
        SweeperRunRepository(session).add(republished, failed)
        session.commit()

    REPUBLISHED.inc(republished)
    FAILED.inc(failed)
    LAST_SUCCESS.set_to_current_time()
    await asyncio.to_thread(push, settings.pushgateway_url, "sweeper", REGISTRY)
    return republished, failed


async def main() -> None:
    async with await mq.connect(settings.rabbitmq_url) as connection:
        channel = await connection.channel()
        await mq.declare_topology(channel)
        while True:
            try:
                republished, failed = await run_pass(channel)
                logger.info("sweep: re-published %d, failed %d", republished, failed)
            except Exception:
                logger.exception("sweep failed, trying again next round")
            await asyncio.sleep(INTERVAL_S)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(main())
