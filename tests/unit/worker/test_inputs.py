import numpy as np

from gemm_queue.worker.inputs import make_inputs


def test_shapes_and_dtype():
    a, b = make_inputs(7, m=30, n=20, k=10)
    assert a.shape == (30, 10)
    assert b.shape == (10, 20)
    assert a.dtype == b.dtype == np.float32


def test_values_in_range():
    a, b = make_inputs(7, 100, 100, 100)
    for x in (a, b):
        assert x.min() >= -1
        assert x.max() < 1


def test_same_seed_same_matrices():
    a1, b1 = make_inputs(42, 16, 16, 16)
    a2, b2 = make_inputs(42, 16, 16, 16)
    np.testing.assert_array_equal(a1, a2)
    np.testing.assert_array_equal(b1, b2)


def test_different_seed_different_matrices():
    a1, _ = make_inputs(1, 16, 16, 16)
    a2, _ = make_inputs(2, 16, 16, 16)
    assert not np.array_equal(a1, a2)
