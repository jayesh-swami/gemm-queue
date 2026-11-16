"""Saves the workers' results into Postgres. Runs as its own service, so it can be
scaled apart from the API: `python -m gemm_queue.results`."""

import asyncio
import logging

from gemm_queue.api.db.session import SessionLocal
from gemm_queue.api.settings import settings
from gemm_queue.common import mq
from gemm_queue.common.metrics import push_forever
from gemm_queue.results.metrics import PUSH_INTERVAL_S, REGISTRY
from gemm_queue.results.result_handler import ResultHandler

logger = logging.getLogger(__name__)

# Results are small DB writes, so a few can be in flight at once.
PREFETCH = 10


async def main() -> None:
    async with await mq.connect(settings.rabbitmq_url) as connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=PREFETCH)
        await mq.declare_topology(channel)
        await mq.consume_results(channel, ResultHandler(SessionLocal).handle)

        logger.info("results consumer ready")
        await push_forever(
            settings.pushgateway_url,
            "results",
            settings.metrics_instance,
            REGISTRY,
            PUSH_INTERVAL_S,
        )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(main())
