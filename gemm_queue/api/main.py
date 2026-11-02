from fastapi import FastAPI

from gemm_queue.api import jobs

app = FastAPI(
    title = "gemm-queue", 
    summary = "API to manage the matrix multiplication kernel jobs."
)

app.include_router(jobs.router)

@app.get("/health")
def health():
    return {"status": "ok :D"}
