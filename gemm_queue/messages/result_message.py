from pydantic import BaseModel

from gemm_queue.enums import Kernel


class ResultMessage(BaseModel):
    """Outcome of one kernel run, sent from the worker to the API on gemm.results."""

    task_id: int
    job_id: int
    kernel: Kernel
    success: bool
    message: str
    ms: float | None = None
    tflops: float | None = None
