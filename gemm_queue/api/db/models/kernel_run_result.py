from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from gemm_queue.api.db.models.base import AuditMixin, Base
from gemm_queue.common.enums import Kernel, RunStatus


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
