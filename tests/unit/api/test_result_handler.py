import pytest

from gemm_queue.api import result_handler
from gemm_queue.api.result_handler import ResultHandler
from gemm_queue.db.repositories import KernelJobRepository
from gemm_queue.enums import Kernel, RunStatus
from gemm_queue.messages import ResultMessage


def result_for(job, kernel: Kernel, success: bool = True) -> ResultMessage:
    run = next(r for r in job.runs if r.kernel == kernel)
    if success:
        return ResultMessage(
            task_id=run.id, job_id=job.id, kernel=kernel, success=True, message="",
            ms=1.0, tflops=2.0, max_error=1e-7, passed=True,
        )
    return ResultMessage(task_id=run.id, job_id=job.id, kernel=kernel, success=False, message="boom")


def load(session_factory, job_id):
    with session_factory() as session:
        return KernelJobRepository(session).get(job_id)


def run_of(job, kernel: Kernel):
    return next(r for r in job.runs if r.kernel == kernel)


class FakeMessage:
    """Records what the handler does with a delivery."""

    def __init__(self, body: bytes) -> None:
        self.body = body
        self.message_id = "1"
        self.acked = False
        self.requeued: bool | None = None

    async def ack(self) -> None:
        self.acked = True

    async def reject(self, requeue: bool) -> None:
        self.requeued = requeue


# --- saving: run and job status rules ---


def test_first_result_marks_the_run_done_and_the_job_running(session_factory, job):
    ResultHandler(session_factory)._save(result_for(job, Kernel.NAIVE))

    saved = load(session_factory, job.id)
    run = run_of(saved, Kernel.NAIVE)
    assert run.status == RunStatus.DONE
    assert (run.ms, run.tflops, run.max_error, run.passed) == (1.0, 2.0, 1e-7, True)
    assert saved.status == RunStatus.RUNNING
    assert saved.finished_at is None


def test_failed_run_keeps_its_error(session_factory, job):
    ResultHandler(session_factory)._save(result_for(job, Kernel.HALF2, success=False))

    run = run_of(load(session_factory, job.id), Kernel.HALF2)
    assert run.status == RunStatus.FAILED
    assert run.error == "boom"
    assert run.ms is None


def test_job_is_done_once_all_runs_are_in_even_if_one_failed(session_factory, job):
    handler = ResultHandler(session_factory)
    for kernel in Kernel:
        handler._save(result_for(job, kernel, success=kernel != Kernel.HALF2))

    saved = load(session_factory, job.id)
    assert saved.status == RunStatus.DONE
    assert saved.finished_at is not None


def test_job_fails_when_every_run_failed(session_factory, job):
    handler = ResultHandler(session_factory)
    for kernel in Kernel:
        handler._save(result_for(job, kernel, success=False))

    assert load(session_factory, job.id).status == RunStatus.FAILED


def test_duplicate_result_changes_nothing(session_factory, job):
    handler = ResultHandler(session_factory)
    for kernel in Kernel:
        handler._save(result_for(job, kernel))
    finished_at = load(session_factory, job.id).finished_at

    handler._save(result_for(job, Kernel.LDS))

    saved = load(session_factory, job.id)
    assert saved.status == RunStatus.DONE
    assert saved.finished_at == finished_at


@pytest.mark.parametrize(("task_id", "job_id"), [(999, None), (None, 999)])
def test_result_for_unknown_run_or_job_is_ignored(session_factory, job, task_id, job_id):
    result = result_for(job, Kernel.NAIVE).model_copy(
        update={"task_id": task_id or job.runs[0].id, "job_id": job_id or job.id}
    )
    ResultHandler(session_factory)._save(result)

    saved = load(session_factory, job.id)
    assert saved.status == RunStatus.QUEUED
    assert all(r.status == RunStatus.QUEUED for r in saved.runs)


# --- handling a delivery: ack, retry or DLQ ---


async def test_valid_result_is_saved_then_acked(session_factory, job):
    message = FakeMessage(result_for(job, Kernel.NAIVE).model_dump_json().encode())
    await ResultHandler(session_factory).handle(message)

    assert message.acked
    assert message.requeued is None
    assert run_of(load(session_factory, job.id), Kernel.NAIVE).status == RunStatus.DONE


async def test_malformed_result_goes_straight_to_the_dlq(session_factory):
    message = FakeMessage(b"not json")
    await ResultHandler(session_factory).handle(message)

    assert not message.acked
    assert message.requeued is False


async def test_db_error_requeues_for_a_retry(job, monkeypatch):
    monkeypatch.setattr(result_handler, "RETRY_DELAY_S", 0)

    def db_down():
        raise ConnectionError("db down")

    message = FakeMessage(result_for(job, Kernel.NAIVE).model_dump_json().encode())
    await ResultHandler(db_down).handle(message)

    assert not message.acked
    assert message.requeued is True
