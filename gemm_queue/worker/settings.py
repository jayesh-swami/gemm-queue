from typing import Literal

from gemm_queue.common.settings import CommonSettings


class WorkerSettings(CommonSettings):
    worker_runner: Literal["fake", "hip"] = "fake"
    kernel_iters: int = 2  # timed runs per task, averaged into ms
    # Tasks a worker runs at once (aio-pika starts each delivery as its own asyncio task).
    # Keep 1 for the GPU: kernels running side by side would distort each other's timings.
    worker_prefetch: int = 1


settings = WorkerSettings()
