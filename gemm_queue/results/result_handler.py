import asyncio
import logging

from aio_pika.abc import AbstractIncomingMessage
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from gemm_queue.api.db.repositories import KernelRunResultRepository
from gemm_queue.common.enums import RunStatus
from gemm_queue.common.messages import ResultMessage
from gemm_queue.results.metrics import RESULTS_SAVED, RUN_SECONDS

logger = logging.getLogger(__name__)

RETRY_DELAY_S = 5


class ResultHandler:
    """Writes result messages from the worker into the DB."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    async def handle(self, message: AbstractIncomingMessage) -> None:
        """Parse -> save (in a thread, the DB code is sync) -> ack.

        A message that can't be parsed never will be, so it goes straight to the DLQ.
        Other errors (e.g. DB down) are retried after a pause; past the delivery
        limit RabbitMQ moves the message to the DLQ too.
        """
        try:
            result = ResultMessage.model_validate_json(message.body)
        except ValidationError:
            logger.exception("result %s is malformed, moving it to the DLQ", message.message_id)
            await message.reject(requeue=False)
            return

        try:
            await asyncio.to_thread(self._save, result)
            await message.ack()
        except Exception:
            logger.exception(
                "saving result %s failed, retrying in %ds", message.message_id, RETRY_DELAY_S
            )
            await asyncio.sleep(RETRY_DELAY_S)
            await message.reject(requeue=True)

    def _save(self, result: ResultMessage) -> None:
        """Write the result into its run's row. The job's status is derived from its
        runs when read, so the job row isn't touched or locked.

        Saving the same result twice gives the same row, so redeliveries are safe.
        """
        status = RunStatus.DONE if result.success else RunStatus.FAILED
        with self._session_factory() as session:
            saved = KernelRunResultRepository(session).save_result(
                run_id=result.task_id,
                job_id=result.job_id,
                status=status,
                ms=result.ms,
                tflops=result.tflops,
                max_error=result.max_error,
                passed=result.passed,
                error=None if result.success else result.message,
            )
            session.commit()

        if saved is None:
            logger.warning("no run %d in job %d, dropping result", result.task_id, result.job_id)
            return
        RESULTS_SAVED.labels(result.kernel.value, status.value).inc()
        RUN_SECONDS.observe((saved.finished_at - saved.created_at).total_seconds())
        logger.info(
            "saved run %d (%s) of job %d: %s", result.task_id, result.kernel, result.job_id, status
        )
