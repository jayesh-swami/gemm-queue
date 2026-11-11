import asyncio
import logging
from datetime import UTC, datetime

from aio_pika.abc import AbstractIncomingMessage
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from gemm_queue.api.db.repositories import KernelJobRepository
from gemm_queue.common.enums import RunStatus
from gemm_queue.common.messages import ResultMessage

logger = logging.getLogger(__name__)

FINISHED = (RunStatus.DONE, RunStatus.FAILED)
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
        """Update the run, then the job's status once all its runs are in.

        Saving the same result twice gives the same rows, so redeliveries are safe.
        """
        with self._session_factory() as session:
            # The lock makes results of the same job save one at a time, so the
            # "are all runs finished?" check always sees the other runs' commits.
            job = KernelJobRepository(session).get_for_update(result.job_id)
            run = next((r for r in job.runs if r.id == result.task_id), None) if job else None
            if run is None:
                logger.warning(
                    "no run %d in job %d, dropping result", result.task_id, result.job_id
                )
                return

            run.status = RunStatus.DONE if result.success else RunStatus.FAILED
            run.ms = result.ms
            run.tflops = result.tflops
            run.max_error = result.max_error
            run.passed = result.passed
            run.error = None if result.success else result.message

            if all(r.status in FINISHED for r in job.runs):
                any_done = any(r.status == RunStatus.DONE for r in job.runs)
                job.status = RunStatus.DONE if any_done else RunStatus.FAILED
                job.finished_at = job.finished_at or datetime.now(UTC)
            else:
                job.status = RunStatus.RUNNING

            session.commit()
            logger.info(
                "saved run %d (%s) of job %d -> job %s", run.id, run.kernel, job.id, job.status
            )
