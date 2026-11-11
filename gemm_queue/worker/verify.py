import numpy as np

from gemm_queue.enums import Kernel

# fp16 kernels round A, B and C to half precision, so they get a looser bound.
TOLERANCE = {
    Kernel.NAIVE: 1e-4,
    Kernel.LDS: 1e-4,
    Kernel.ROCBLAS: 1e-4,
    Kernel.HALF2: 2e-3,
    Kernel.ROCBLAS_HALF: 2e-3,
}


def max_error(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """Largest |C - A @ B| as a fraction of the largest |A @ B|, computed in float64."""
    ref = a.astype(np.float64) @ b.astype(np.float64)
    return float(np.max(np.abs(c - ref)) / np.max(np.abs(ref)))
