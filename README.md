# gemm-queue

A small job system for running GPU matrix-multiplication kernels. You submit M, N and K in a web page; the API queues one task per kernel on RabbitMQ; a GPU worker runs five AMD HIP and rocBLAS kernels, checks every result against NumPy, and the timings come back to the page.

The kernels are the workload. The project is mostly about the system around them: queueing, retries, dead-letter handling, and making sure results are never silently lost.

```mermaid
block-beta
  columns 8
  space:2 DB[("Postgres")] space SW["Sweeper<br/>every 60 s"]:2 space:2
  space:8
  B["Browser"] space API["API<br/>FastAPI + results consumer"] space
  block:MQ:2
    columns 2
    MQL["RabbitMQ"]:2
    T[["gemm.tasks"]]:2
    R[["gemm.results"]]:2
    TD[["gemm.tasks.dlq"]] RD[["gemm.results.dlq"]]
  end
  space W["GPU workers<br/>1 to N"]
  space:8
  block:MON:8
    columns 3
    MONL["Monitoring"]:3
    PGW["Pushgateway"] P["Prometheus"] G["Grafana"]
    space PE["postgres-exporter"] space
  end
  B -- "POST /jobs<br/>GET /jobs/:id" --> API
  API -- "jobs and runs" --> DB
  API -- "5 tasks per job" --> T
  T --> W
  W -- "result, then ack" --> R
  R --> API
  SW -- "stuck runs" --> DB
  SW -- "re-publish" --> T
  PGW --> P
  PE --> P
  P --> G
  style MQL fill:none,stroke:none
  style MONL fill:none,stroke:none
```

One job through the system:

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant A as API (FastAPI)
    participant DB as Postgres
    participant Q as RabbitMQ
    participant W as GPU worker
    B->>A: POST /jobs (M, N, K)
    A->>DB: save job + 5 runs
    A->>Q: 5 tasks on gemm.tasks
    A-->>B: 202, job id
    loop for each kernel
        Q->>W: task
        W->>W: run kernel, check against NumPy
        W->>Q: result on gemm.results
        W->>Q: ack task
        Q->>A: result (results consumer)
        A->>DB: save run
    end
    B->>A: poll GET /jobs/:id
    A-->>B: runs with timings
```

## Design

- **At-least-once delivery.** The worker acks a task only after its result is published, and results are written by task ID, so a redelivered task or a duplicate result changes nothing.
- **Dead-letter queues on both sides.** A task that keeps failing goes to `gemm.tasks.dlq` after 4 attempts; a malformed result goes straight to `gemm.results.dlq`. Database errors are retried with a pause instead of burning through the delivery limit.
- **Row lock per job.** Results of one job are saved in parallel, so the job row is locked while a run is written. An integration test reproduces the race without the lock (5 of 5 runs left jobs stuck) and passes with it.
- **Sweeper batch job.** Every 60 s it looks for runs with no result after 10 minutes, re-publishes their task, and marks them failed after 3 attempts, so every job ends as done or failed.
- **Metrics.** The API serves `/metrics` for Prometheus to pull; the worker and sweeper push theirs to a Pushgateway; RabbitMQ and Postgres are scraped through their exporters. Each sweeper pass is also logged in a `sweeper_runs` table.
- **Pluggable runner.** `HipRunner` calls the compiled HIP binary; `FakeRunner` returns the NumPy product, so the whole pipeline runs and is tested without a GPU.

## Results

One 8192 × 8192 × 8192 job on a Radeon 8060S (gfx1151, ROCm 7.2.1), averaged over 5 timed runs after a warm-up:

| Kernel | Time | TFLOPS | Max relative error |
|---|---|---|---|
| naive | 3670 ms | 0.30 | 4.3e-6 |
| lds (shared-memory tiles) | 1009 ms | 1.09 | 4.3e-6 |
| half2 (packed fp16) | 438 ms | 2.51 | 4.9e-4 |
| rocBLAS sgemm | 506 ms | 2.17 | 4.4e-6 |
| rocBLAS fp16 | 37 ms | 29.6 | 4.9e-4 |

`half2` stores A and B in fp16, so it beats rocBLAS sgemm at the cost of precision. It needs even K and N; other sizes fail on purpose and the error is shown on the page.

## Running it

Needs Podman with Compose, [uv](https://docs.astral.sh/uv/), Node and, for the GPU worker, an AMD GPU with ROCm.

```sh
cp .env.example .env     # set the passwords and API_KEY
make up                  # builds both images, starts Postgres, RabbitMQ, API, worker, sweeper and monitoring
make load-test           # optional: submit 20 jobs to watch
```

Then open http://localhost:8000 for the app and http://localhost:3000 for the Grafana dashboard. For a GPU other than gfx1151, run `make up GPU_ARCH=gfx1100` (or whatever `rocminfo` reports).

The number of workers and their runner can be set when starting:

```sh
make up WORKERS=4 RUNNER=fake   # 4 workers that return the NumPy product instead of using the GPU
make worker WORKERS=1           # scale back to one worker, runner from WORKER_RUNNER in .env
```

Without a GPU, run the worker on the host with the fake runner:

```sh
make db mq build-frontend migrate
make run-api                         # in one terminal
WORKER_RUNNER=fake make run-worker   # in another
```

## Tests

```sh
make test               # 75 unit tests, no services needed
make test-integration   # 11 tests against real Postgres and RabbitMQ (make db mq first)
make lint               # ruff, oxlint and pre-commit checks
```

## Layout

```
gemm_queue/common/    shared settings, enums, messages, RabbitMQ helpers
gemm_queue/api/       FastAPI routes, results consumer, database, migrations
gemm_queue/worker/    task handler, runners, HIP kernel source
gemm_queue/batch/     sweeper (batch job)
gemm_queue/frontend/  React + Vite page
deploy/               docker-compose.yml, the two Dockerfiles, Prometheus and Grafana config
tests/                unit/ and integration/
```
