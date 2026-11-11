from abc import ABC, abstractmethod

import numpy as np

from gemm_queue.common.enums import Kernel
from gemm_queue.worker.kernel_output_dto import KernelOutputDto


class KernelRunner(ABC):
    """Runs one GEMM kernel: C = A @ B, with A of shape (M, K) and B of (K, N).

    Inputs and output are float32. M, N and K come from the array shapes.
    """

    @abstractmethod
    async def run(self, kernel: Kernel, a: np.ndarray, b: np.ndarray) -> KernelOutputDto: ...
