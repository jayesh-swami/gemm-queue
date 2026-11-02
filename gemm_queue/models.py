from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from gemm_queue.enums import Kernel, RunStatus

class AuditMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Base(DeclarativeBase):
    pass


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

    runs: Mapped[list["KernelRunResult"]] = relationship(
        back_populates="job", lazy="selectin"
    )


class KernelRunResult(Base, AuditMixin):
    __tablename__ = "results"
    __table_args__ = (UniqueConstraint("job_id", "kernel", name="uq_results_job_id_kernel"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    status: Mapped[RunStatus] = mapped_column(default=RunStatus.QUEUED)
    kernel: Mapped[Kernel]
    ms: Mapped[float | None]
    tflops: Mapped[float | None]
    max_error: Mapped[float | None]
    passed: Mapped[bool | None]
    error: Mapped[str | None] = mapped_column(Text)

    job: Mapped["KernelJob"] = relationship(back_populates="runs")
