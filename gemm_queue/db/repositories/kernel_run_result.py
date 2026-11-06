from sqlalchemy.orm import Session

from gemm_queue.db.models import KernelRunResult


class KernelRunResultRepository:
    """Repositories don't commit; the caller owns the transaction."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, run_id: int) -> KernelRunResult | None:
        return self.session.get(KernelRunResult, run_id)
