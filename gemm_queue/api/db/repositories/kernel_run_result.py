from datetime import datetime

from sqlalchemy import Row, func, update
from sqlalchemy.orm import Session

from gemm_queue.api.db.models import KernelJob, KernelRunResult
from gemm_queue.common.enums import RunStatus

# Bulk UPDATEs: the session holds no copies of these rows to keep in sync.
NO_SYNC = {"synchronize_session": False}


class KernelRunResultRepository:
    """Repositories don't commit; the caller owns the transaction."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, run_id: int) -> KernelRunResult | None:
        return self.session.get(KernelRunResult, run_id)

    def save_result(
        self,
        run_id: int,
        job_id: int,
        status: RunStatus,
        ms: float | None,
        tflops: float | None,
        max_error: float | None,
        passed: bool | None,
        error: str | None,
    ) -> Row | None:
        """Write a run's result: one UPDATE by id, no read first, no lock on the job.

        No other result writes this row, so results of the same job don't wait
        for each other. A real result always wins, even over the sweeper's
        "failed". Returns (created_at, finished_at), or None if there's no such run.
        """
        stmt = (
            update(KernelRunResult)
            .where(KernelRunResult.id == run_id, KernelRunResult.job_id == job_id)
            .values(
                status=status,
                ms=ms,
                tflops=tflops,
                max_error=max_error,
                passed=passed,
                error=error,
                finished_at=func.coalesce(KernelRunResult.finished_at, func.now()),
            )
            .returning(KernelRunResult.created_at, KernelRunResult.finished_at)
        )
        return self.session.execute(stmt, execution_options=NO_SYNC).one_or_none()

    def fail_stuck(self, cutoff: datetime, max_attempts: int, error: str) -> int:
        """Fail queued runs untouched since cutoff that have used all their attempts.

        The conditions are in the UPDATE itself (compare-and-set): a run whose
        result is saved meanwhile no longer matches and is left alone.
        """
        stmt = (
            update(KernelRunResult)
            .where(
                KernelRunResult.status == RunStatus.QUEUED,
                KernelRunResult.updated_at < cutoff,
                KernelRunResult.attempts >= max_attempts,
            )
            .values(status=RunStatus.FAILED, error=error, finished_at=func.now())
            .returning(KernelRunResult.id)
        )
        return len(self.session.execute(stmt, execution_options=NO_SYNC).all())

    def claim_stuck(self, cutoff: datetime, max_attempts: int) -> list[Row]:
        """Count one more attempt for queued runs untouched since cutoff, and return
        what's needed to publish their tasks again. Compare-and-set, like fail_stuck.

        The bump also refreshes updated_at, which restarts the run's timeout.
        """
        stmt = (
            update(KernelRunResult)
            .where(
                KernelRunResult.job_id == KernelJob.id,
                KernelRunResult.status == RunStatus.QUEUED,
                KernelRunResult.updated_at < cutoff,
                KernelRunResult.attempts < max_attempts,
            )
            .values(attempts=KernelRunResult.attempts + 1)
            .returning(
                KernelRunResult.id,
                KernelRunResult.job_id,
                KernelRunResult.kernel,
                KernelJob.m,
                KernelJob.n,
                KernelJob.k,
                KernelJob.seed,
            )
        )
        return list(self.session.execute(stmt, execution_options=NO_SYNC).all())
