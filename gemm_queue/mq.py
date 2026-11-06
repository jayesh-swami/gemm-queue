import aio_pika
from aio_pika.abc import AbstractChannel, AbstractRobustConnection

from gemm_queue.config import settings
from gemm_queue.messages import TaskMessage

TASKS_QUEUE = "gemm.tasks"
RESULTS_QUEUE = "gemm.results"
TASKS_DLQ = "gemm.tasks.dlq"

MAX_TASK_REDELIVERIES = 3

PUBLISH_TIMEOUT_S = 5

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


async def publish_task(channel: AbstractChannel, task: TaskMessage) -> None:
    # Returns once the broker confirms the message is stored. Raises if the
    # broker nacks it, no queue matches (mandatory), or no confirm arrives in time.
    await channel.default_exchange.publish(
        aio_pika.Message(
            task.model_dump_json().encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            message_id=str(task.task_id),
        ),
        routing_key=TASKS_QUEUE,
        timeout=PUBLISH_TIMEOUT_S,
    )
