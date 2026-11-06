import asyncio
import logging
import secrets
from typing import Annotated

from aio_pika.abc import AbstractChannel
from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from gemm_queue import mq
from gemm_queue.api.constants import MAX_SEED
from gemm_queue.api.dependencies import get_mq_channel
from gemm_queue.api.schema import JobCreated, JobRequest
from gemm_queue.api.security import require_api_key
from gemm_queue.crud import save_job
from gemm_queue.messages import TaskMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", status_code=202, dependencies=[Depends(require_api_key)])
async def create_job(
    req: JobRequest,
    channel: Annotated[AbstractChannel, Depends(get_mq_channel)],
) -> JobCreated:
    seed = req.seed if req.seed is not None else secrets.randbelow(MAX_SEED + 1)

    # Commit first, then publish: a worker must never receive a task whose row
    # doesn't exist yet. The DB driver is sync, so it runs off the event loop.
    job = await run_in_threadpool(save_job, req.m, req.n, req.k, seed)

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
