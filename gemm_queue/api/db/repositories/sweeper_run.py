from sqlalchemy.orm import Session

from gemm_queue.api.db.models import SweeperRun


class SweeperRunRepository:
    """Repositories don't commit; the caller owns the transaction."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, republished: int, failed: int) -> SweeperRun:
        run = SweeperRun(republished=republished, failed=failed)
        self.session.add(run)
        return run
