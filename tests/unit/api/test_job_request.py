import pytest
from pydantic import ValidationError

from gemm_queue.api.constants import MAX_DIM, MAX_SEED
from gemm_queue.api.schema import JobRequest


def test_valid_request_without_seed():
    req = JobRequest(m=1, n=MAX_DIM, k=300)
    assert req.seed is None


def test_seed_bounds():
    assert JobRequest(m=1, n=1, k=1, seed=0).seed == 0
    assert JobRequest(m=1, n=1, k=1, seed=MAX_SEED).seed == MAX_SEED
    with pytest.raises(ValidationError):
        JobRequest(m=1, n=1, k=1, seed=MAX_SEED + 1)
    with pytest.raises(ValidationError):
        JobRequest(m=1, n=1, k=1, seed=-1)


@pytest.mark.parametrize("bad", [0, -5, MAX_DIM + 1])
@pytest.mark.parametrize("dim", ["m", "n", "k"])
def test_dims_out_of_range_are_rejected(dim, bad):
    sizes = {"m": 8, "n": 8, "k": 8, dim: bad}
    with pytest.raises(ValidationError):
        JobRequest(**sizes)


def test_missing_dim_is_rejected():
    with pytest.raises(ValidationError):
        JobRequest(m=8, n=8)


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        JobRequest(m=8, n=8, k=8, iters=100)
