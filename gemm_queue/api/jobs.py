import asyncio
import logging
import secrets
from typing import Annotated

from aio_pika.abc import AbstractChannel
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from gemm_queue import mq
from gemm_queue.api.constants import MAX_SEED
from gemm_queue.api.dependencies import get_db_session, get_mq_channel
from gemm_queue.api.schema import JobCreated, JobDetail, JobRequest
from gemm_queue.api.security import require_api_key
from gemm_queue.db.repositories import KernelJobRepository
from gemm_queue.messages import TaskMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", status_code=202, dependencies=[Depends(require_api_key)])
async def create_job(
    req: JobRequest,
    session: Annotated[Session, Depends(get_db_session)],
    channel: Annotated[AbstractChannel, Depends(get_mq_channel)],
) -> JobCreated:
    seed = req.seed if req.seed is not None else secrets.randbelow(MAX_SEED + 1)

    # add() only stages the rows in memory; the commit is the database I/O.
    job = KernelJobRepository(session).add(m=req.m, n=req.n, k=req.k, seed=seed)

    # Commit first, then publish: a worker must never receive a task whose row
    # doesn't exist yet. The DB driver is sync, so it runs off the event loop.
    await run_in_threadpool(session.commit)

    tasks = [
        TaskMessage(
            task_id=run.id,
            job_id=job.id,
            kernel=run.kernel,
            m=job.m,
            n=job.n,
            k=job.k,
            seed=job.seed,
        )
        for run in job.runs
    ]
    try:
        await asyncio.gather(*(mq.publish_task(channel, task) for task in tasks))
    except Exception:
        # The job is already saved, so the request still succeeds. Its tasks
        # stay queued in Postgres for the re-publish sweeper to pick up.
        logger.exception("job %d saved but publishing its tasks failed", job.id)

    return JobCreated(job_id=job.id, seed=seed)


@router.get("", dependencies=[Depends(require_api_key)])
def list_jobs(
    session: Annotated[Session, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[JobDetail]:
    """Recent jobs, newest first, each with its kernel runs."""
    jobs = KernelJobRepository(session).list_recent(limit, offset)
    return [JobDetail.model_validate(job) for job in jobs]


@router.get("/{job_id}", dependencies=[Depends(require_api_key)])
def get_job(job_id: int, session: Annotated[Session, Depends(get_db_session)]) -> JobDetail:
    """One job with all its kernel runs. A plain def, so FastAPI runs it in its thread pool."""
    job = KernelJobRepository(session).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobDetail.model_validate(job)
