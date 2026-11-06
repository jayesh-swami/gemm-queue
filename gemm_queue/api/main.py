from contextlib import asynccontextmanager

from fastapi import FastAPI

from gemm_queue import mq
from gemm_queue.api import jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One connection and channel for the app's lifetime, shared by all requests.
    # The channel has publisher confirms on (aio-pika's default).
    connection = await mq.connect()
    channel = await connection.channel()
    await mq.declare_topology(channel)
    app.state.mq_channel = channel
    yield
    await connection.close()


app = FastAPI(
    title = "gemm-queue",
    summary = "API to manage the matrix multiplication kernel jobs.",
    lifespan=lifespan,
)

app.include_router(jobs.router)

@app.get("/health")
def health():
    return {"status": "ok :D"}
