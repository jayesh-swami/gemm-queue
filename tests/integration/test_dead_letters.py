import asyncio

from helpers import get_one, publish_raw, wait_until

from gemm_queue import mq


def test_malformed_result_is_dead_lettered_right_away():
    asyncio.run(publish_raw(mq.RESULTS_QUEUE, b"not json"))
    body = wait_until(lambda: asyncio.run(get_one(mq.RESULTS_DLQ)), timeout=10)
    assert body == b"not json"


def test_task_that_keeps_failing_is_dead_lettered_after_retries():
    # The worker can't parse it, rejects it each time, and after the delivery
    # limit (4 attempts) RabbitMQ moves it to the DLQ.
    asyncio.run(publish_raw(mq.TASKS_QUEUE, b"not json"))
    body = wait_until(lambda: asyncio.run(get_one(mq.TASKS_DLQ)), timeout=20)
    assert body == b"not json"
