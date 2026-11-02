from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from gemm_queue.api.constants import MAX_DIM, MAX_SEED
from gemm_queue.enums import Kernel, RunStatus

Dim = Annotated[int, Field(ge=1, le=MAX_DIM, description="Matrix dimension")]
Seed = Annotated[int, Field(ge=0, le=MAX_SEED)]


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    m: Dim
    k: Dim
    n: Dim
    seed: Seed | None = None


class JobCreated(BaseModel):
    job_id: int
    seed: int


class KernelRun(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kernel: Kernel
    status: RunStatus
    ms: float | None = None
    tflops: float | None = None
    max_error: float | None = None
    passed: bool | None = None
    error: str | None = None


class JobDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: int = Field(validation_alias="id")
    m: int
    k: int
    n: int
    seed: int
    status: RunStatus
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    kernel_runs: list[KernelRun] = Field(validation_alias="runs")
