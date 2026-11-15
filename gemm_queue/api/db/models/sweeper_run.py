from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from gemm_queue.api.db.models.base import Base


class SweeperRun(Base):
    """One sweeper pass and what it did. Append-only."""

    __tablename__ = "sweeper_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    republished: Mapped[int]
    failed: Mapped[int]
