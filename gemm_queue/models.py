from sqlalchemy import DateTime, func, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from datetime import datetime
from gemm_queue.enums import RunStatus, Kernel

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
    mat_1_src: Mapped[str] = mapped_column(String(200))
    mat_2_src: Mapped[str] = mapped_column(String(200))
    m: Mapped[int]
    n: Mapped[int]
    k: Mapped[int]

    runs: Mapped[list["KernelRunResult"]] = relationship(back_populates = "job")

class KernelRunResult(Base, AuditMixin):
    __tablename__ = "results"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    status: Mapped[RunStatus] = mapped_column(default = RunStatus.QUEUED)
    kernel: Mapped[Kernel]
    ms: Mapped[float | None]
    tflops: Mapped[float | None]

    job: Mapped["KernelJob"] = relationship(back_populates = "runs")
