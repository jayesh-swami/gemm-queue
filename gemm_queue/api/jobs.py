import secrets

from fastapi import APIRouter, Depends

from gemm_queue.api.constants import MAX_SEED
from gemm_queue.api.schema import JobCreated, JobRequest
from gemm_queue.api.security import require_api_key
from gemm_queue.db import SessionLocal
from gemm_queue.enums import Kernel
from gemm_queue.models import KernelJob, KernelRunResult

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.post("", status_code=202, dependencies=[Depends(require_api_key)])
def create_job(req: JobRequest) -> JobCreated:

    seed = req.seed if req.seed is not None else secrets.randbelow(MAX_SEED + 1)

    with SessionLocal() as session:
        job = KernelJob(
            m=req.m,
            n=req.n,
            k=req.k,
            seed=seed,
            runs=[KernelRunResult(kernel=kernel) for kernel in Kernel],
        )
        session.add(job)
        session.commit()

    # next: publish one RabbitMQ message per run

    return JobCreated(job_id=job.id, seed=seed)
