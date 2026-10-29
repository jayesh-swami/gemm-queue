import enum

class JobStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"

class Kernel(enum.StrEnum):
    NAIVE = "naive"
    LDS = "lds"
    HALF2 = "half2"
    ROCBLAS = "rocblas"
    ROCBLAS_HALF = "rocblas_half"
