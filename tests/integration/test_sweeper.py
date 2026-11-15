"""The sweeper against real Postgres and RabbitMQ, with the fake worker running.

Jobs are inserted straight into the DB without publishing, as if POST /jobs had
failed to publish, and backdated so the sweeper sees them as stuck.
"""

import asyncio

from helpers import wait_until
from sqlalchemy import text

from gemm_queue.api.db.repositories import KernelJobRepository
from gemm_queue.api.db.session import SessionLocal, dbEngine
from gemm_queue.api.settings import settings
from gemm_queue.batch import sweeper
from gemm_queue.common import mq
from gemm_queue.common.enums import RunStatus


def add_job(attempts: int = 1, stuck: bool = True) -> int:
    with SessionLocal() as session:
        job = KernelJobRepository(session).add(m=16, n=16, k=16, seed=1)
        session.commit()
    with dbEngine.begin() as conn:
        conn.execute(
            text("UPDATE results SET attempts = :a WHERE job_id = :id"),
            {"a": attempts, "id": job.id},
        )
        if stuck:
            conn.execute(
                text(
                    "UPDATE results SET updated_at = now() - interval '1 hour' WHERE job_id = :id"
                ),
                {"id": job.id},
            )
    return job.id


def load(job_id: int):
    with SessionLocal() as session:
        return KernelJobRepository(session).get(job_id)


def sweep() -> tuple[int, int]:
    async def run():
        async with await mq.connect(settings.rabbitmq_url) as connection:
            return await sweeper.sweep_once(await connection.channel())

    return asyncio.run(run())


def test_lost_tasks_are_republished_and_the_job_finishes():
    job_id = add_job()

    assert sweep() == (5, 0)

    job = wait_until(lambda: (j := load(job_id)).status == RunStatus.DONE and j)
    assert all(r.attempts == 2 for r in job.runs)


def test_runs_out_of_attempts_are_failed():
    job_id = add_job(attempts=sweeper.MAX_ATTEMPTS)

    assert sweep() == (0, 5)

    job = load(job_id)
    assert job.status == RunStatus.FAILED
    assert all(r.error == "no result after 3 attempts" for r in job.runs)


def test_recent_runs_are_left_alone():
    job_id = add_job(stuck=False)

    assert sweep() == (0, 0)
    assert load(job_id).status == RunStatus.QUEUED
