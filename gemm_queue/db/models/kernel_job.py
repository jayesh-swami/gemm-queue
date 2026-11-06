from datetime import datetime

from sqlalchemy import DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gemm_queue.db.models.base import AuditMixin, Base
from gemm_queue.db.models.kernel_run_result import KernelRunResult
from gemm_queue.enums import RunStatus


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
    runs: Mapped[list[KernelRunResult]] = relationship(lazy="selectin")
