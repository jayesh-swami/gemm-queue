from sqlalchemy.orm import Session

from gemm_queue.db.models import KernelJob, KernelRunResult
from gemm_queue.enums import Kernel


class KernelJobRepository:
    """Repositories don't commit; the caller owns the transaction."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, m: int, n: int, k: int, seed: int) -> KernelJob:
        """Stage a new job with one queued run per kernel."""
        job = KernelJob(
            m=m,
            n=n,
            k=k,
            seed=seed,
            runs=[KernelRunResult(kernel=kernel) for kernel in Kernel],
        )
        self.session.add(job)
        return job

    def get(self, job_id: int) -> KernelJob | None:
        return self.session.get(KernelJob, job_id)
