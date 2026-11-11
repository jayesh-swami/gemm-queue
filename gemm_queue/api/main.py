from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from gemm_queue.api.consumers.result_handler import ResultHandler
from gemm_queue.api.db.session import SessionLocal
from gemm_queue.api.routes import jobs
from gemm_queue.api.settings import settings
from gemm_queue.common import mq

# Results are small DB writes, so a few can be in flight at once.
RESULTS_PREFETCH = 10

FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One connection and channel for the app's lifetime, shared by all requests.
    # The channel has publisher confirms on (aio-pika's default).
    connection = await mq.connect(settings.rabbitmq_url)
    channel = await connection.channel()
    await mq.declare_topology(channel)
    app.state.mq_channel = channel

    # Separate channel for consuming, with its own prefetch.
    results_channel = await connection.channel()
    await results_channel.set_qos(prefetch_count=RESULTS_PREFETCH)
    await mq.consume_results(results_channel, ResultHandler(SessionLocal).handle)

    yield
    await connection.close()


app = FastAPI(
    title="gemm-queue",
    summary="API to manage the matrix multiplication kernel jobs.",
    lifespan=lifespan,
)

app.include_router(jobs.router)


@app.get("/health")
def health():
    return {"status": "ok :D"}


# The built frontend (make build-frontend), served at /. Mounted last so the API
# routes above win; skipped if it hasn't been built.
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
