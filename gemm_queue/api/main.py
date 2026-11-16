import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.orm import Session

from gemm_queue.api.dependencies import get_db_session
from gemm_queue.api.metrics import HTTP_REQUESTS, HTTP_SECONDS
from gemm_queue.api.routes import jobs
from gemm_queue.api.settings import settings
from gemm_queue.common import mq

FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One connection and channel for the app's lifetime, shared by all requests.
    # The channel has publisher confirms on (aio-pika's default).
    connection = await mq.connect(settings.rabbitmq_url)
    app.state.mq_connection = connection
    channel = await connection.channel()
    await mq.declare_topology(channel)
    app.state.mq_channel = channel

    yield
    await connection.close()


app = FastAPI(
    title="gemm-queue",
    summary="API to manage the matrix multiplication kernel jobs.",
    lifespan=lifespan,
)

app.include_router(jobs.router)


@app.middleware("http")
async def record_request(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    # The route template (/jobs/{job_id}), not the raw path, so label values stay few.
    route = getattr(request.scope.get("route"), "path", None) or "static"
    HTTP_REQUESTS.labels(request.method, route, response.status_code).inc()
    HTTP_SECONDS.labels(request.method, route).observe(time.perf_counter() - start)
    return response


@app.get("/health")
def health():
    """Liveness: the process is up."""
    return {"status": "ok :D"}


@app.get("/ready")
def ready(request: Request, session: Annotated[Session, Depends(get_db_session)]):
    """Readiness: Postgres answers and the RabbitMQ connection is open."""
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unreachable") from exc
    connection = getattr(request.app.state, "mq_connection", None)
    if connection is None or connection.is_closed:
        raise HTTPException(status_code=503, detail="RabbitMQ unreachable")
    return {"status": "ready"}


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    """Prometheus scrapes this."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# The built frontend (make build-frontend), served at /. Mounted last so the API
# routes above win; skipped if it hasn't been built.
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
