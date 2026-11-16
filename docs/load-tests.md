# Load tests

16 Nov 2026. Baseline before moving the results consumer out of the API.

**Setup:** everything runs on one machine (32 CPU threads): Postgres, RabbitMQ, the API, 8 workers, the monitoring stack and the load generator. The workers use the fake runner with 64 × 64 × 64 matrices, so these numbers measure the system around the kernels, not the GPU. SQL logging is off. Each test was run once.

## Summary

| Part | Capacity |
|---|---|
| 8 workers | ~2,000 tasks/s |
| API taking jobs, nothing else to do | ~430 jobs/s (2,140 tasks/s) |
| API taking jobs while also saving results | ~200 jobs/s (1,000 tasks/s) |
| Results consumer, nothing else to do | ~630 results/s |
| Results consumer while the API takes jobs | ~290 results/s |

- **The API process is the bottleneck.** It handles `POST /jobs` and runs the results consumer, and it never used more than ~1.2 CPU cores. Python runs one thread at a time, so the two jobs share roughly one core.
- **Results pile up because of that.** About 1,000 tasks/s go in, but only ~290 results/s get saved, so `gemm.results` grows by ~700 messages a second during a run.
- **The workers were never the limit.** `gemm.tasks` never held more than 25 messages while the API was taking jobs.
- **Saving results halves how fast the API accepts jobs:** 430 jobs/s without it, 200 with it.

## 1. API: how many jobs it accepts

Each load process sends `POST /jobs` as fast as it can, waiting for each response before sending the next. Numbers are from a 40 s window after an 8 s warm-up.

| Processes | Jobs/s | Tasks/s | Mean latency | p95 latency | API CPU (cores) |
|---|---|---|---|---|---|
| 10 | 203 | 1,014 | 45 ms | 71 ms | 1.16 |
| 20 | 202 | 1,011 | 93 ms | 225 ms | 1.18 |
| 40 | 194 | 968 | 200 ms | 249 ms | 1.17 |
| 80 | 194 | 968 | 405 ms | 488 ms | 1.17 |

Throughput stays at ~200 jobs/s from 10 to 80 processes, and latency doubles every time the processes double. So the API was already at its limit with 10 processes. Extra requests only wait longer.

This fits Little's law (jobs/s = requests in flight / latency): 10 / 45 ms ≈ 220, and 80 / 405 ms ≈ 200.

With 10 processes the p95 latency still looked fine (71 ms). In a test like this, where each client waits for its answer, latency alone doesn't show that the server is full. The flat throughput does.

## 2. Results consumer: how fast it saves results

| Processes sending jobs | Saved/s during the run | Backlog when the load stopped | Time to empty it | Saved/s while emptying |
|---|---|---|---|---|
| 10 | 304 | 33,165 | 54 s | 618 |
| 20 | 283 | 31,624 | 56 s | 616 |
| 40 | 278 | 30,313 | 51 s | 648 |
| 80 | 275 | 30,206 | 52 s | 636 |

After the load stops, the API has only the results to work on. It then saves about twice as fast (~630/s) and uses about one full core.

## 3. Workers: how fast they process tasks

To measure the workers by themselves, they need a full queue to work from:

1. Stop all 8 workers.
2. Send 20,000 jobs (100,000 tasks). This took 46.7 s, which is 428 jobs/s. The workers were stopped, so the API had no results to save and could take jobs at twice its usual rate.
3. Start the 8 workers and time how long they take to empty `gemm.tasks`.

| | |
|---|---|
| Tasks in the queue | 100,000 |
| Time to empty it | ~55 s |
| Worker throughput (Prometheus, 5 s samples) | 1,905 to 2,029 tasks/s, steady |
| Peak `gemm.results` backlog | ~68,000 |
| All results saved | 156 s after the workers started (~650 results/s) |

The sweeper re-published nothing during these tests: every run finished on its first attempt. The longest any run waited for its result was about 3.5 minutes (in the worker test), inside the sweeper's 10 minute timeout.

## What to do next

Move the results consumer into its own service. These numbers suggest:

- The API should then accept close to the 430 jobs/s it reached when it had no results to save.
- One consumer process should save ~630 results/s. Keeping up with 2,140 tasks/s would take about 4 of them, if they scale evenly.
- With several consumers, the 5 results of one job will compete for the job row lock. That's the next likely limit.

The test to repeat afterwards: the same API sweep with 1, 2 and 4 results consumers.

## How it was measured

With `scripts/bench.py` (`api 10 20 40 80`, then `worker`).

- **API numbers:** counters and the latency histogram read straight from the API's `/metrics` at the start and end of each window. The p95 values are estimated from the histogram buckets, so they are approximate. The mean latency is exact.
- **Queue depths:** `rabbitmqctl list_queues` every 0.5 s. RabbitMQ updates these counts every few seconds for quorum queues, so the depths lag slightly.
- **Worker throughput:** `rate(worker_tasks_total)` from the worker metrics in Prometheus.
- **Caveats:**
  - The load generator shares the machine with everything it tests.
  - Each client waits for its answer before sending the next request, so it never overloads the API beyond the number of processes.
  - Each test was run once.
