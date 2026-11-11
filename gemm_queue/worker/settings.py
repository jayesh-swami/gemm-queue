from typing import Literal

from gemm_queue.common.settings import CommonSettings


class WorkerSettings(CommonSettings):
    worker_runner: Literal["fake", "hip"] = "fake"
    kernel_iters: int = 2  # timed runs per task, averaged into ms


settings = WorkerSettings()
