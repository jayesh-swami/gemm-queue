import numpy as np
import pytest

from gemm_queue.common.enums import Kernel
from gemm_queue.worker.inputs import make_inputs
from gemm_queue.worker.runners import FakeRunner
from gemm_queue.worker.runners.fake_runner import FAKE_MS


@pytest.mark.parametrize("kernel", list(Kernel))
async def test_returns_the_product_with_a_timing_near_its_canned_value(kernel):
    a, b = make_inputs(3, 40, 30, 20)
    out = await FakeRunner().run(kernel, a, b)

    assert out.success
    assert out.message == ""
    np.testing.assert_allclose(out.c, a @ b, rtol=1e-6)
    assert 0.9 * FAKE_MS[kernel] <= out.ms <= 1.1 * FAKE_MS[kernel]


@pytest.mark.parametrize(("k", "n"), [(21, 30), (20, 31), (21, 31)])
async def test_half2_fails_on_odd_k_or_n(k, n):
    a, b = make_inputs(3, 40, n, k)
    out = await FakeRunner().run(Kernel.HALF2, a, b)

    assert not out.success
    assert out.message == "half2 needs K and N to be even"
    assert out.c is None
    assert out.ms is None


async def test_odd_sizes_are_fine_for_other_kernels():
    a, b = make_inputs(3, 41, 31, 21)
    out = await FakeRunner().run(Kernel.LDS, a, b)
    assert out.success
