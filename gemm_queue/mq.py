import aio_pika
from aio_pika.abc import AbstractChannel, AbstractRobustConnection

from gemm_queue.config import settings

TASKS_QUEUE = "gemm.tasks"
RESULTS_QUEUE = "gemm.results"
TASKS_DLQ = "gemm.tasks.dlq"

MAX_TASK_REDELIVERIES = 3

QUORUM = {"x-queue-type": "quorum"}


async def connect() -> AbstractRobustConnection:
    return await aio_pika.connect_robust(settings.rabbitmq_url)


async def declare_topology(channel: AbstractChannel) -> None:
    await channel.declare_queue(TASKS_DLQ, durable=True, arguments=QUORUM)
    await channel.declare_queue(
        TASKS_QUEUE,
        durable=True,
        arguments={
            **QUORUM,
            "x-delivery-limit": MAX_TASK_REDELIVERIES,
            # "" is the default exchange, which routes by queue name
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": TASKS_DLQ,
        },
    )
    await channel.declare_queue(RESULTS_QUEUE, durable=True, arguments=QUORUM)
