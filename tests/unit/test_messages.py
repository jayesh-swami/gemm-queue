"""The queue messages. The results consumer relies on bad input raising ValidationError
(it sends those straight to the DLQ), so that's tested here too."""

import pytest
from pydantic import ValidationError

from gemm_queue.enums import Kernel
from gemm_queue.messages import ResultMessage, TaskMessage


def test_task_round_trips_through_json():
    task = TaskMessage(task_id=1, job_id=2, kernel=Kernel.HALF2, m=3, n=4, k=5, seed=6)
    assert TaskMessage.model_validate_json(task.model_dump_json()) == task


def test_failed_result_round_trips_with_empty_numbers():
    result = ResultMessage(
        task_id=1,
        job_id=2,
        kernel=Kernel.HALF2,
        success=False,
        message="half2 needs K and N to be even",
    )
    parsed = ResultMessage.model_validate_json(result.model_dump_json())
    assert parsed == result
    assert parsed.ms is None and parsed.passed is None


def test_kernel_parses_from_its_string_value():
    raw = '{"task_id":1,"job_id":2,"kernel":"rocblas_half","m":3,"n":4,"k":5,"seed":6}'
    assert TaskMessage.model_validate_json(raw).kernel is Kernel.ROCBLAS_HALF


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        '{"task_id":1,"job_id":2,"kernel":"naive"}',  # missing success and message
        '{"task_id":1,"job_id":2,"kernel":"turbo","success":true,"message":""}',  # unknown kernel
    ],
)
def test_malformed_result_raises_validation_error(raw):
    with pytest.raises(ValidationError):
        ResultMessage.model_validate_json(raw)
