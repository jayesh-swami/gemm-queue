import asyncio
import logging

from gemm_queue.common import mq
from gemm_queue.common.metrics import push_forever
from gemm_queue.worker.metrics import PUSH_INTERVAL_S, REGISTRY
from gemm_queue.worker.runners import FakeRunner, HipRunner
from gemm_queue.worker.settings import settings
from gemm_queue.worker.task_handler import TaskHandler

logger = logging.getLogger(__name__)


async def main() -> None:
    """Connect, then process up to WORKER_PREFETCH tasks at a time until stopped."""
    runner = (
        HipRunner(iters=settings.kernel_iters) if settings.worker_runner == "hip" else FakeRunner()
    )

    async with await mq.connect(settings.rabbitmq_url) as connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=settings.worker_prefetch)
        await mq.declare_topology(channel)
        await mq.consume_tasks(channel, TaskHandler(runner, channel).handle)

        logger.info(
            "worker ready (%s runner, prefetch %d)",
            settings.worker_runner,
            settings.worker_prefetch,
        )
        await push_forever(
            settings.pushgateway_url,
            "worker",
            settings.metrics_instance,
            REGISTRY,
            PUSH_INTERVAL_S,
        )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(main())
