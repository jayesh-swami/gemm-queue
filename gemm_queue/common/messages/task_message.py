from pydantic import BaseModel

from gemm_queue.common.enums import Kernel


class TaskMessage(BaseModel):
    """One kernel run, sent from the API to the worker on gemm.tasks."""

    task_id: int
    job_id: int
    kernel: Kernel
    m: int
    n: int
    k: int
    seed: int
