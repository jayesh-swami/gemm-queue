import time
from collections.abc import Callable

import aio_pika

from gemm_queue.api.settings import settings
from gemm_queue.common import mq
from gemm_queue.common.messages import ResultMessage


def wait_until[T](predicate: Callable[[], T], timeout: float = 20.0, interval: float = 0.2) -> T:
    """Call predicate until it returns something truthy, and return that."""
    deadline = time.monotonic() + timeout
    while True:
        value = predicate()
        if value:
            return value
        if time.monotonic() > deadline:
            raise AssertionError(f"condition not met within {timeout}s")
        time.sleep(interval)


async def publish_raw(queue: str, body: bytes) -> None:
    async with await mq.connect(settings.rabbitmq_url) as connection:
        channel = await connection.channel()
        await channel.default_exchange.publish(
            aio_pika.Message(body, message_id="test"), routing_key=queue
        )


async def publish_results(results: list[ResultMessage]) -> None:
    """Publish all at once, so the consumer gets them as one burst."""
    async with await mq.connect(settings.rabbitmq_url) as connection:
        channel = await connection.channel()
        for result in results:
            await mq.publish_result(channel, result)


async def get_one(queue: str) -> bytes | None:
    """Take one message off a queue, or None if it's empty."""
    async with await mq.connect(settings.rabbitmq_url) as connection:
        channel = await connection.channel()
        message = await (await channel.get_queue(queue)).get(no_ack=True, fail=False)
        return message.body if message else None


async def purge(*queues: str) -> None:
    async with await mq.connect(settings.rabbitmq_url) as connection:
        channel = await connection.channel()
        for queue in queues:
            await (await channel.get_queue(queue)).purge()
