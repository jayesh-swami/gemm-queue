# Load tests

Last run: 16 Nov 2026, after the results consumer moved into its own service. The numbers get updated as improvements land; the history is at the end.

**Setup:** one machine with 32 CPU threads runs everything: Postgres, RabbitMQ, the API, the workers, the results consumers, monitoring and the load generator. The workers use the fake runner on 64 × 64 × 64 matrices, so this measures the system around the kernels, not the GPU. Each run was done once.

**Method:**
1. Measure each part at its peak, on its own.
2. Run the whole system under load.
3. Compare the two. The whole system can't be faster than its slowest part. If it is slower than every part, something they share (RabbitMQ, Postgres, the machine) is the limit.

All numbers are in tasks/s (one job = 5 tasks), so the parts can be compared.

## Summary

| Part | Peak on its own |
|---|---|
| API (one process) | ~410 jobs/s = **~2,050 tasks/s** |
| 16 workers | **~2,570 tasks/s** |
| 8 results consumers | **~3,040 results/s** (4: ~2,140) |
| RabbitMQ | never above 1.2 cores |
| Postgres | never above 1.8 cores |
| **Whole system** (16 workers, 4 or 8 consumers) | **285–340 jobs/s = 1,400–1,700 tasks/s**, queues stay empty |

- **The API is the bottleneck.** It has the lowest peak, and in the whole-system runs it sits at ~1.1 CPU cores: one Python process, which runs Python code on one core at a time. Adding load processes from 10 to 160 doesn't raise throughput; it only makes requests wait longer.
- **Everything behind the API has room.** The workers and the consumers both have higher peaks, and RabbitMQ and Postgres use little CPU.
- **4 results consumers are enough for what the API can send.** They save results as fast as they arrive (1,500/s, backlog under 60). 2 consumers fall behind. More than 4 still adds capacity (8 do ~3,040/s in the drain test), it just isn't needed while the API is the limit.
- **The machine is never full.** At most 13 of 32 cores were busy. Each part spends most of its time waiting: on Python's GIL, on a row lock, on disk syncs, on round trips to RabbitMQ.

## 1. Each part at its peak

### API: how many jobs it accepts

With the workers stopped, the API only accepts jobs and publishes tasks. Nothing else competes with it. Filling the queue with 20,000 jobs took 47–50 s:

| Run | Jobs/s | Tasks/s |
|---|---|---|
| 1 | 411 | 2,056 |
| 2 | 424 | 2,120 |
| 3 | 398 | 1,991 |

### Workers: the drain test

Stop the workers, fill `gemm.tasks` with 100,000 tasks, start N workers and measure how fast the queue empties (the slope while it drains from 80% to 20%).

| Workers | Tasks/s | Per worker | Worker CPU (all of them) |
|---|---|---|---|
| 4 | 945 | 236 | 0.7 cores |
| 8 | 1,696 | 212 | 1.6 cores |
| 16 | 2,569 | 161 | 3.6 cores |

More workers help, but each one does less: 236 → 161 tasks/s. A worker takes one task at a time and spends most of it waiting (0.23 cores each): for the next delivery, and for RabbitMQ to confirm the result is stored. Why that wait grows with more workers isn't proven yet. RabbitMQ isn't short of CPU, so the likely cause is something it does one message at a time per queue, such as writing each message to disk.

### Results consumers: the drain test

Stop the consumers, let the workers fill `gemm.results` with 100,000 results, start N consumers and measure how fast it empties.

| Consumers | Results/s | Per consumer | Consumer CPU | Postgres CPU |
|---|---|---|---|---|
| 1 | 665 | 665 | 1.0 | 0.2 |
| 2 | 1,319 | 659 | 1.8 | 0.4 |
| 4 | 2,142 | 536 | 3.3 | 0.7 |
| 8 | 3,044 | 381 | 6.4 | 1.5 |

Up to 2 consumers scale evenly; after that each adds less. Every save locks its job's row, so the 5 results of one job wait for each other. During a load run with 8 consumers, Postgres showed up to 8 sessions waiting on that lock, plus waits on disk syncs at commit.

## 2. The whole system

16 workers, N consumers, and `load.py` sending `POST /jobs` as fast as it can from P processes. Each run is a 40 s window after an 8 s warm-up.

| Consumers | Load processes | Jobs/s in | Results saved/s | Results backlog at the end | Mean / p95 latency | API CPU |
|---|---|---|---|---|---|---|
| 1 | 10 | 384 | 579 | 52,273 (growing) | 24 / 46 ms | 1.06 |
| 1 | 80 | 338 | 578 | 42,540 (growing) | 233 / 345 ms | 1.10 |
| 2 | 40 | 315 | 1,011 | 24,307 (growing) | 122 / 242 ms | 1.13 |
| 4 | 40 | 300 | 1,502 | 58 | 129 / 242 ms | 1.12 |
| 8 | 10 | 338 | 1,691 | 24 | 27 / 48 ms | 1.06 |
| 8 | 40 | 310 | 1,547 | 26 | 125 / 242 ms | 1.12 |
| 8 | 160 | 285 | 1,427 | 30 | 552 / 737 ms | 1.11 |

- With 1 or 2 consumers, results arrive faster than they are saved and the backlog grows. From 4 consumers on, they keep up.
- With 8 consumers, going from 10 to 160 load processes doesn't raise throughput, while the mean latency goes from 27 ms to 552 ms. That's what a full server looks like: requests just wait longer. Little's law fits (jobs/s = requests in flight / latency): 10 / 27 ms ≈ 370 and 160 / 552 ms ≈ 290.
- The API accepts fewer jobs here (285–384/s) than on its own (~410/s). Why it slows down when the rest of the system is busy isn't explained yet. The machine had spare cores.

## 3. The bottleneck

| | Tasks/s |
|---|---|
| API alone | ~2,050 |
| 16 workers alone | ~2,570 |
| 4 / 8 consumers alone | ~2,140 / ~3,040 |
| **Whole system** | **1,400–1,700** |

The API has the lowest peak, and in the whole system it is the part running flat out (~1.1 cores) while everything else has room. So the API is the bottleneck. It's a single Python process, and Python runs one thread's code at a time, so that process can't use more than about one core.

The whole system runs below even the API's own peak (1,400–1,700 vs ~2,050), because the API slows down when the rest is busy. That gap is the open question in section 2.

## History

**Before: the results consumer ran inside the API process** (16 Nov 2026, morning; 8 workers, 1 consumer):

| | Before | After (now) |
|---|---|---|
| API intake under load | ~200 jobs/s | 285–340 jobs/s (with 4+ consumers) |
| Results saved under load | ~290/s, backlog grew ~700/s | keeps up with 4+ consumers |
| Results consumer on its own | ~630/s, could not scale | 665/s each; 8 do ~3,040/s |

Taking jobs and saving results shared one process and one core, so saving results halved how fast the API accepted jobs (430 jobs/s with no results to save, 200 with them). Moving the consumer into its own service raised API intake by 40–70% and made the consumers scalable.

## What we learned about measuring

- **The measuring tool can be the load.** The first runs read queue depths with `podman exec mq rabbitmqctl` twice a second. Each call starts an Erlang VM inside the RabbitMQ container: 3.1 cores of CPU while polling, against 0.25 idle. That made RabbitMQ look like it was using 4–7 cores and seem to be the bottleneck. Reading depths from RabbitMQ's HTTP API instead costs nothing measurable. RabbitMQ's own scheduler statistics confirmed it was ~90% idle.
- **Latency can look fine on a full server.** Each load process waits for its answer before sending the next request. At 10 processes, p95 was under 50 ms while the API was already at its limit. The flat throughput as processes are added is what shows it.
- **A load test shows only the slowest part's capacity.** In the whole-system run, 4 and 8 consumers both saved ~1,500/s, because that's all that arrived. Only the drain test, which gives a part a full queue, shows what it can do.

## Later improvements

To try, then rerun these tests:

| Idea | What it should change |
|---|---|
| Scale the API (see below) | intake above ~410 jobs/s; then the workers (~2,570 tasks/s at 16, about 510 jobs/s) become the limit |
| Remove the job row lock: derive a job's status from its runs when it's read | consumers scale closer to evenly |
| RabbitMQ: classic instead of quorum queues (one node, so no replication is lost), worker prefetch 2, fewer log lines | more tasks/s per worker |
| Kubernetes, with KEDA scaling workers and consumers on queue depth | replicas follow the load; the maximums come from the tables above |

### Scaling the API

The API is one Python process, and Python runs one thread's code at a time (the GIL), so it tops out at about one core. Three ways past that, from least to most effort:

1. **More processes in the container: `uvicorn --workers N`.** Each process gets its own event loop and core; the OS spreads connections across them. A one-line change in `deploy/api.Dockerfile`, plus:
   - **Metrics:** each process keeps its own counters, so `/metrics` would answer for whichever process got the scrape. `prometheus_client`'s multiprocess mode (`PROMETHEUS_MULTIPROC_DIR`) adds them up; without it the dashboard and `bench.py` would be wrong.
   - **Connections:** each process opens its own RabbitMQ connection and DB pool (5 + 10). Four processes can use 60 Postgres connections, under the default limit of 100.
   - **Migrations:** they run once in the start command before uvicorn forks, so they stay safe.
2. **More API containers behind a load balancer.** Like the workers, but Compose can't publish port 8000 from several containers, so something has to spread the requests: nginx, Caddy or Traefik in Compose, a Service in Kubernetes. Migrations move out of the API's start command into a one-off step, so replicas starting together don't run them at the same time. Each replica is scraped on its own. Unlike option 1, replicas can run on different machines and survive one of them failing.
3. **Make each request cheaper.** Each job costs the API about 2.5–3 ms of CPU (1.1 cores / ~380 jobs/s). Profile where it goes (e.g. `py-spy` on the running process) before changing anything. Candidates:
   - five publishes per job, each waiting for its own confirm (batch them, or publish one message per job and fan out later);
   - six ORM inserts per job (one bulk insert);
   - Pydantic, JSON and an access-log line per request (`--no-access-log` is free to try);
   - the sync DB driver running in a thread pool (an async driver avoids the hand-off).

Start with option 1 and the multiprocess metrics, then rerun `bench.py api`. Option 2 comes with the Kubernetes step.

## How it was measured

```sh
make up RUNNER=fake WORKERS=16 RESULTS=4
uv run python scripts/bench.py api 10 40 160   # whole system, per number of load processes
uv run python scripts/bench.py worker          # worker drain (uses the running workers)
uv run python scripts/bench.py results         # consumer drain (uses the running consumers)
```

Scale between runs with `make worker WORKERS=N RUNNER=fake` and `make results RESULTS=N`.

- **Throughput:** jobs accepted from the API's `/metrics`; results saved by counting rows in Postgres; drain rates from the slope of the queue depth.
- **Latency:** from the API's request histogram. The mean is exact; p95 is estimated from the histogram buckets.
- **CPU:** per service from `podman stats` (replicas added up); the whole machine from `/proc/stat`.
- **Queue depths:** RabbitMQ's management API every 0.5 s. RabbitMQ refreshes these counts every few seconds, so depths lag slightly; slopes aren't affected.
- **Caveats:**
  - The load generator runs on the same machine as everything it tests.
  - Each load process waits for its answer before sending the next request, so the load never exceeds the number of processes.
  - Each run was done once.
  - The "before" numbers were measured with the `rabbitmqctl` polling described above.
