from gemm_queue.db import SessionLocal
from gemm_queue.enums import Kernel
from gemm_queue.models import KernelJob, KernelRunResult


def save_job(m: int, n: int, k: int, seed: int) -> KernelJob:
    """Insert a job with one queued run per kernel, and commit."""
    with SessionLocal() as session:
        job = KernelJob(
            m=m,
            n=n,
            k=k,
            seed=seed,
            runs=[KernelRunResult(kernel=kernel) for kernel in Kernel],
        )
        session.add(job)
        session.commit()
    return job
