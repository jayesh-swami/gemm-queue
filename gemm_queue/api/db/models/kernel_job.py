from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column, relationship

from gemm_queue.api.db.models.base import AuditMixin, Base
from gemm_queue.api.db.models.kernel_run_result import KernelRunResult
from gemm_queue.common.enums import RunStatus

FINISHED = (RunStatus.DONE, RunStatus.FAILED)


class KernelJob(Base, AuditMixin):
    """A job's status isn't stored: it's derived from its runs when read.

    Each result then writes only its own run row, so results of the same job can
    be saved in parallel without locking the job.
    """

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    m: Mapped[int]
    n: Mapped[int]
    k: Mapped[int]
    seed: Mapped[int]

    # One-way on purpose: a run refers to its job only by job_id, so the two
    # model modules don't import each other.
    runs: Mapped[list[KernelRunResult]] = relationship(lazy="selectin", order_by=KernelRunResult.id)

    @property
    def status(self) -> RunStatus:
        """Queued until a run finishes, running until all have, then done if any
        succeeded and failed if none did."""
        finished = [r for r in self.runs if r.status in FINISHED]
        if len(finished) < len(self.runs):
            return RunStatus.RUNNING if finished else RunStatus.QUEUED
        return (
            RunStatus.DONE
            if any(r.status == RunStatus.DONE for r in finished)
            else RunStatus.FAILED
        )

    @property
    def finished_at(self) -> datetime | None:
        """When the last run finished, once all have."""
        if self.status not in FINISHED:
            return None
        return max((r.finished_at for r in self.runs if r.finished_at), default=None)
