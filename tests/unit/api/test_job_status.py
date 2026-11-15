from gemm_queue.api.db.models import KernelJob, KernelRunResult
from gemm_queue.common.enums import Kernel, RunStatus

Q, D, F = RunStatus.QUEUED, RunStatus.DONE, RunStatus.FAILED


def job_with(*statuses: RunStatus) -> KernelJob:
    return KernelJob(
        m=1, n=1, k=1, seed=0,
        runs=[KernelRunResult(kernel=k, status=s) for k, s in zip(Kernel, statuses, strict=False)],
    )  # fmt: skip


def test_nothing_finished_stays_queued():
    job = job_with(Q, Q, Q, Q, Q)
    job.refresh_status()
    assert job.status == Q
    assert job.finished_at is None


def test_some_finished_is_running():
    job = job_with(D, F, Q, Q, Q)
    job.refresh_status()
    assert job.status == RunStatus.RUNNING
    assert job.finished_at is None


def test_all_finished_with_one_success_is_done():
    job = job_with(F, F, F, F, D)
    job.refresh_status()
    assert job.status == D
    assert job.finished_at is not None


def test_all_failed_is_failed():
    job = job_with(F, F, F, F, F)
    job.refresh_status()
    assert job.status == F


def test_finished_at_is_kept_on_refresh():
    job = job_with(D, D, D, D, D)
    job.refresh_status()
    first = job.finished_at
    job.refresh_status()
    assert job.finished_at == first
