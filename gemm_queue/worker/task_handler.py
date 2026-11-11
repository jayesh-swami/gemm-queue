import asyncio
import logging

from aio_pika.abc import AbstractChannel, AbstractIncomingMessage

from gemm_queue import mq
from gemm_queue.messages import ResultMessage, TaskMessage
from gemm_queue.worker.inputs import make_inputs
from gemm_queue.worker.kernel_runner import KernelRunner

logger = logging.getLogger(__name__)


class TaskHandler:
    """Turns one task message into one result message."""

    def __init__(self, runner: KernelRunner, channel: AbstractChannel) -> None:
        self._runner = runner
        self._channel = channel

    async def handle(self, message: AbstractIncomingMessage) -> None:
        """Build inputs -> run the kernel -> publish the result -> ack.

        A kernel failure is a normal (failed) result. Any other error sends the
        task back to the queue; after too many attempts it lands in the DLQ.
        """
        try:
            task = TaskMessage.model_validate_json(message.body)
            a, b = await asyncio.to_thread(make_inputs, task.seed, task.m, task.n, task.k)
            out = await self._runner.run(task.kernel, a, b)

            tflops = None
            if out.success:
                tflops = 2 * task.m * task.n * task.k / (out.ms / 1e3) / 1e12

            result = ResultMessage(
                task_id=task.task_id,
                job_id=task.job_id,
                kernel=task.kernel,
                success=out.success,
                message=out.message,
                ms=out.ms,
                tflops=tflops,
            )
            await mq.publish_result(self._channel, result)
            await message.ack()
            logger.info(
                "task %d: %s %dx%dx%d success=%s ms=%s",
                task.task_id, task.kernel, task.m, task.n, task.k, out.success, out.ms,
            )
        except Exception:
            logger.exception("task %s failed, sending it back to the queue", message.message_id)
            await message.reject(requeue=True)
