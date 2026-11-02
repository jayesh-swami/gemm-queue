from fastapi import FastAPI

app = FastAPI(
    title = "gemm-queue", 
    summary = "API to manage the matrix multiplication kernel jobs."
)

@app.get("/health")
def health():
    return {"status": "ok :D"}
