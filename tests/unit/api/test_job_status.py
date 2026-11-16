from datetime import UTC, datetime, timedelta

from gemm_queue.api.db.models import KernelJob, KernelRunResult
from gemm_queue.common.enums import Kernel, RunStatus

Q, D, F = RunStatus.QUEUED, RunStatus.DONE, RunStatus.FAILED
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def job_with(*statuses: RunStatus) -> KernelJob:
    """A job whose i-th finished run finished at T0 + i seconds."""
    runs = [
        KernelRunResult(
            kernel=kernel,
            status=status,
            finished_at=T0 + timedelta(seconds=i) if status != Q else None,
        )
        for i, (kernel, status) in enumerate(zip(Kernel, statuses, strict=False))
    ]
    return KernelJob(m=1, n=1, k=1, seed=0, runs=runs)


def test_nothing_finished_is_queued():
    job = job_with(Q, Q, Q, Q, Q)
    assert job.status == Q
    assert job.finished_at is None


def test_some_finished_is_running():
    job = job_with(D, F, Q, Q, Q)
    assert job.status == RunStatus.RUNNING
    assert job.finished_at is None


def test_all_finished_with_one_success_is_done():
    job = job_with(F, F, F, F, D)
    assert job.status == D
    assert job.finished_at == T0 + timedelta(seconds=4)  # the last run to finish


def test_all_failed_is_failed():
    job = job_with(F, F, F, F, F)
    assert job.status == F
    assert job.finished_at is not None
