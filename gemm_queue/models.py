from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from datetime import datetime
from gemm-queue.enums import JobStatus

class AuditMixin:

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

class Base(DeclarativeBase):
    pass

class Job(Base, AuditMixin):
    __tablename__ = "jobs"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[JobStatus] = mapped_column(String(30))
