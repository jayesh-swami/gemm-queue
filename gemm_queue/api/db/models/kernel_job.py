from datetime import UTC, datetime

from sqlalchemy import DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gemm_queue.api.db.models.base import AuditMixin, Base
from gemm_queue.api.db.models.kernel_run_result import KernelRunResult
from gemm_queue.common.enums import RunStatus


class KernelJob(Base, AuditMixin):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    m: Mapped[int]
    n: Mapped[int]
    k: Mapped[int]
    seed: Mapped[int]
    status: Mapped[RunStatus] = mapped_column(default=RunStatus.QUEUED)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)

    # One-way on purpose: a run refers to its job only by job_id, so the two
    # model modules don't import each other.
    runs: Mapped[list[KernelRunResult]] = relationship(lazy="selectin", order_by=KernelRunResult.id)

    def refresh_status(self) -> None:
        """Derive the job's status from its runs.

        Queued until a run finishes, running until all have, then done if any
        succeeded and failed if none did.
        """
        finished = [r for r in self.runs if r.status in (RunStatus.DONE, RunStatus.FAILED)]
        if len(finished) < len(self.runs):
            self.status = RunStatus.RUNNING if finished else RunStatus.QUEUED
            return
        any_done = any(r.status == RunStatus.DONE for r in finished)
        self.status = RunStatus.DONE if any_done else RunStatus.FAILED
        self.finished_at = self.finished_at or datetime.now(UTC)
