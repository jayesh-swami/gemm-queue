import asyncio
import random

import numpy as np

from gemm_queue.enums import Kernel
from gemm_queue.worker.kernel_output_dto import KernelOutputDto
from gemm_queue.worker.kernel_runner import KernelRunner

FAKE_MS = {
    Kernel.NAIVE: 100.0,
    Kernel.LDS: 30.0,
    Kernel.HALF2: 15.0,
    Kernel.ROCBLAS: 5.0,
    Kernel.ROCBLAS_HALF: 2.0,
}


class FakeRunner(KernelRunner):
    """GPU-free runner: returns the correct product with made-up timings."""

    async def run(self, kernel: Kernel, a: np.ndarray, b: np.ndarray) -> KernelOutputDto:
        k, n = b.shape
        if kernel == Kernel.HALF2 and (k % 2 or n % 2):
            return KernelOutputDto.failed("half2 needs K and N to be even")

        c = await asyncio.to_thread(np.matmul, a, b)
        ms = FAKE_MS[kernel] * random.uniform(0.9, 1.1)
        return KernelOutputDto.ok(c, ms)
