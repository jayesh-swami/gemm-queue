"""Re-publishes runs whose result never arrived; fails them after MAX_ATTEMPTS.

Run with `python -m gemm_queue.batch.sweeper`. Covers tasks that were never
published, landed in a DLQ, or got lost, so every job eventually finishes.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from aio_pika.abc import AbstractChannel

from gemm_queue.api.db.repositories import KernelRunResultRepository, SweeperRunRepository
from gemm_queue.api.db.session import SessionLocal
from gemm_queue.batch.metrics import FAILED, LAST_SUCCESS, REGISTRY, REPUBLISHED
from gemm_queue.batch.settings import settings
from gemm_queue.common import mq
from gemm_queue.common.messages import TaskMessage
from gemm_queue.common.metrics import push

logger = logging.getLogger(__name__)

# A queued run untouched for this long is treated as lost (default 10 min).
STUCK_AFTER = timedelta(seconds=settings.sweeper_stuck_after_s)
MAX_ATTEMPTS = 3
INTERVAL_S = settings.sweeper_interval_s


async def sweep_once(channel: AbstractChannel) -> tuple[int, int]:
    """One pass. Returns (re-published, failed).

    Both steps are single UPDATEs that check the run is still queued and stuck
    (compare-and-set), so a result saved at the same moment always wins and no
    job is locked. The transaction stays open while the claimed tasks are
    published: if publishing fails (RabbitMQ down), the rollback gives the
    attempts back. If the commit fails after publishing, a task goes out twice,
    which saving by task id makes harmless.

    The DB calls are sync and block the loop briefly; nothing else runs here.
    """
    cutoff = datetime.now(UTC) - STUCK_AFTER
    with SessionLocal() as session:
        repo = KernelRunResultRepository(session)
        failed = repo.fail_stuck(cutoff, MAX_ATTEMPTS, f"no result after {MAX_ATTEMPTS} attempts")
        claimed = repo.claim_stuck(cutoff, MAX_ATTEMPTS)
        for run in claimed:
            task = TaskMessage(
                task_id=run.id,
                job_id=run.job_id,
                kernel=run.kernel,
                m=run.m,
                n=run.n,
                k=run.k,
                seed=run.seed,
            )
            await mq.publish_task(channel, task)
        session.commit()
    return len(claimed), failed


async def run_pass(channel: AbstractChannel) -> tuple[int, int]:
    """sweep_once, then log the pass in sweeper_runs and push the metrics."""
    republished, failed = await sweep_once(channel)
    with SessionLocal() as session:
        SweeperRunRepository(session).add(republished, failed)
        session.commit()

    REPUBLISHED.inc(republished)
    FAILED.inc(failed)
    LAST_SUCCESS.set_to_current_time()
    await asyncio.to_thread(
        push, settings.pushgateway_url, "sweeper", settings.metrics_instance, REGISTRY
    )
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
