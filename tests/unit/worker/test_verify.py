import numpy as np

from gemm_queue.enums import Kernel
from gemm_queue.worker.inputs import make_inputs
from gemm_queue.worker.verify import TOLERANCE, max_error

FP32_KERNELS = [Kernel.NAIVE, Kernel.LDS, Kernel.ROCBLAS]
FP16_KERNELS = [Kernel.HALF2, Kernel.ROCBLAS_HALF]


def as_fp16_kernel(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """What the half kernels do: fp16 inputs, fp32 accumulation, fp16 output."""
    a16 = a.astype(np.float16).astype(np.float32)
    b16 = b.astype(np.float16).astype(np.float32)
    return (a16 @ b16).astype(np.float16).astype(np.float32)


def test_every_kernel_has_a_tolerance():
    assert set(TOLERANCE) == set(Kernel)


def test_exact_product_has_tiny_error():
    a, b = make_inputs(1, 64, 48, 80)
    assert max_error(a, b, a @ b) < 1e-6


def test_fp32_product_passes_fp32_kernels():
    a, b = make_inputs(1, 256, 192, 300)
    error = max_error(a, b, a @ b)
    for kernel in FP32_KERNELS:
        assert error <= TOLERANCE[kernel]


def test_fp16_product_passes_half_kernels_only():
    a, b = make_inputs(1, 256, 192, 300)
    error = max_error(a, b, as_fp16_kernel(a, b))
    for kernel in FP16_KERNELS:
        assert error <= TOLERANCE[kernel]
    # fp16 rounding is too coarse for the fp32 bound; that's why half kernels get their own
    for kernel in FP32_KERNELS:
        assert error > TOLERANCE[kernel]


def test_one_wrong_element_fails_even_the_fp16_bound():
    a, b = make_inputs(1, 512, 512, 512)
    c = a @ b
    c[100, 200] += 1.0
    assert max_error(a, b, c) > TOLERANCE[Kernel.HALF2]


def test_nan_fails():
    a, b = make_inputs(1, 32, 32, 32)
    c = a @ b
    c[0, 0] = np.nan
    assert not max_error(a, b, c) <= TOLERANCE[Kernel.HALF2]
