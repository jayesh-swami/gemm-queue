import asyncio
import logging

from gemm_queue import mq
from gemm_queue.config import settings
from gemm_queue.worker.runners import FakeRunner, HipRunner
from gemm_queue.worker.task_handler import TaskHandler

logger = logging.getLogger(__name__)


async def main() -> None:
    """Connect, then process tasks one at a time until stopped."""
    runner = HipRunner() if settings.worker_runner == "hip" else FakeRunner()

    async with await mq.connect() as connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=1)
        await mq.declare_topology(channel)
        await mq.consume_tasks(channel, TaskHandler(runner, channel).handle)

        logger.info("worker ready (%s runner)", settings.worker_runner)
        await asyncio.Future()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(main())
