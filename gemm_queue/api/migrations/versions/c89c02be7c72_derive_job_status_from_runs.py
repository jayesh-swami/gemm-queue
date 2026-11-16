"""derive job status from runs

Revision ID: c89c02be7c72
Revises: 7a486e3adf37
Create Date: 2026-11-16 20:38:40.707357

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c89c02be7c72'
down_revision: Union[str, Sequence[str], None] = '7a486e3adf37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    A job's status is derived from its runs from now on, so each result writes only
    its own run row. Runs get their own finished_at, backfilled from updated_at for
    runs already finished (nothing touches a finished run's row afterwards).
    jobs.started_at and jobs.error were never set.
    """
    op.add_column('results', sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE results SET finished_at = updated_at WHERE status IN ('DONE', 'FAILED')")
    op.drop_column('jobs', 'started_at')
    op.drop_column('jobs', 'status')
    op.drop_column('jobs', 'error')
    op.drop_column('jobs', 'finished_at')


def downgrade() -> None:
    """Downgrade schema: store the job status again, computed from the runs."""
    op.add_column('jobs', sa.Column('started_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True))
    op.add_column('jobs', sa.Column('status', postgresql.ENUM('QUEUED', 'RUNNING', 'DONE', 'FAILED', name='runstatus', create_type=False), autoincrement=False, nullable=False, server_default='QUEUED'))
    op.alter_column('jobs', 'status', server_default=None)
    op.add_column('jobs', sa.Column('error', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('jobs', sa.Column('finished_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True))
    op.execute("""
        UPDATE jobs j SET
            status = CASE
                WHEN s.finished = 0 THEN 'QUEUED'
                WHEN s.finished < s.total THEN 'RUNNING'
                WHEN s.any_done THEN 'DONE'
                ELSE 'FAILED'
            END::runstatus,
            finished_at = CASE WHEN s.finished = s.total THEN s.last END
        FROM (
            SELECT job_id,
                   count(*) AS total,
                   count(*) FILTER (WHERE status IN ('DONE', 'FAILED')) AS finished,
                   bool_or(status = 'DONE') AS any_done,
                   max(finished_at) AS last
            FROM results GROUP BY job_id
        ) s
        WHERE s.job_id = j.id
    """)
    op.drop_column('results', 'finished_at')
