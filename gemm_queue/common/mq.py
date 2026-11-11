from collections.abc import Awaitable, Callable

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage, AbstractRobustConnection

from gemm_queue.common.messages import ResultMessage, TaskMessage

TASKS_QUEUE = "gemm.tasks"
RESULTS_QUEUE = "gemm.results"
TASKS_DLQ = "gemm.tasks.dlq"
RESULTS_DLQ = "gemm.results.dlq"

MAX_TASK_REDELIVERIES = 3
# The results consumer waits between retries, so this rides out a short DB outage.
MAX_RESULT_REDELIVERIES = 10

PUBLISH_TIMEOUT_S = 5

QUORUM = {"x-queue-type": "quorum"}


async def connect(url: str) -> AbstractRobustConnection:
    return await aio_pika.connect_robust(url)


async def declare_topology(channel: AbstractChannel) -> None:
    await _declare_with_dlq(channel, TASKS_QUEUE, TASKS_DLQ, MAX_TASK_REDELIVERIES)
    await _declare_with_dlq(channel, RESULTS_QUEUE, RESULTS_DLQ, MAX_RESULT_REDELIVERIES)


async def _declare_with_dlq(
    channel: AbstractChannel, queue: str, dlq: str, max_redeliveries: int
) -> None:
    """A queue whose rejected or over-delivered messages move to `dlq` instead of being dropped."""
    await channel.declare_queue(dlq, durable=True, arguments=QUORUM)
    await channel.declare_queue(
        queue,
        durable=True,
        arguments={
            **QUORUM,
            "x-delivery-limit": max_redeliveries,
            # "" is the default exchange, which routes by queue name
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": dlq,
        },
    )


async def publish_task(channel: AbstractChannel, task: TaskMessage) -> None:
    await _publish(channel, TASKS_QUEUE, task.model_dump_json(), task.task_id)


async def publish_result(channel: AbstractChannel, result: ResultMessage) -> None:
    await _publish(channel, RESULTS_QUEUE, result.model_dump_json(), result.task_id)


async def consume_tasks(
    channel: AbstractChannel, callback: Callable[[AbstractIncomingMessage], Awaitable[None]]
) -> None:
    queue = await channel.get_queue(TASKS_QUEUE)
    await queue.consume(callback)


async def consume_results(
    channel: AbstractChannel, callback: Callable[[AbstractIncomingMessage], Awaitable[None]]
) -> None:
    queue = await channel.get_queue(RESULTS_QUEUE)
    await queue.consume(callback)


async def _publish(channel: AbstractChannel, queue: str, body: str, message_id: int) -> None:
    # Returns once the broker confirms the message is stored. Raises if the
    # broker nacks it, no queue matches (mandatory), or no confirm arrives in time.
    await channel.default_exchange.publish(
        aio_pika.Message(
            body.encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            message_id=str(message_id),
        ),
        routing_key=queue,
        timeout=PUBLISH_TIMEOUT_S,
    )
