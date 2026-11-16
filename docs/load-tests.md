# Load tests

Last run: 16 Nov 2026, after the job status stopped being stored (no more lock per job). The numbers get updated as improvements land; the history is at the end.

**Setup:** one machine with 32 CPU threads runs everything: Postgres, RabbitMQ, the API, the workers, the results consumers, monitoring and the load generator. The workers use the fake runner on 64 × 64 × 64 matrices, so this measures the system around the kernels, not the GPU. Each run was done once.

**Method:**
1. Measure each part at its peak, on its own.
2. Run the whole system under load.
3. Compare the two. The whole system can't be faster than its slowest part. If it is slower than every part, something they share (RabbitMQ, Postgres, the machine) is the limit.

All numbers are in tasks/s (one job = 5 tasks), so the parts can be compared.

## Summary

| Part | Peak on its own |
|---|---|
| API, 1 process | ~410 jobs/s = **~2,050 tasks/s** |
| API, 2 / 4 / 8 processes | ~760 / ~1,380 / ~2,070 jobs/s = **~3,800 / ~6,900 / ~10,350 tasks/s** |
| 16 workers, prefetch 1 | **~2,570 tasks/s** |
| 16 workers, prefetch 4 | **~5,850 tasks/s** |
| 8 results consumers | **~4,740 results/s** (4: ~3,410) |
| RabbitMQ | never above 2 cores |
| Postgres | up to 4.2 cores (8 consumers draining) |
| **Whole system**, 16 workers, 8 consumers, 1 API process | **~1,500 tasks/s**, queues stay empty |
| **Whole system**, same, 2 API processes | **~2,000 tasks/s**, queues stay empty |
| **Whole system**, 4 API processes, prefetch 2–10, job lock | ~2,050 tasks/s saved, ~3,550 accepted, `gemm.results` grows |
| **Whole system**, 4 API processes, prefetch 4, no job lock | **~3,100 tasks/s**, queues stay small, 25 of 32 threads busy |

- **With one API process, the API is the bottleneck.** It runs flat out at ~1.1 cores, because one Python process runs Python code on one core at a time. Adding load processes from 10 to 160 doesn't raise throughput; it only makes requests wait longer.
- **More processes scale the API almost evenly.** Each process uses about one more core; on its own the API goes from ~410 to ~760 to ~1,380 jobs/s with 1, 2 and 4.
- **From 4 API processes on, the workers were the bottleneck.** The API accepts ~3,600 tasks/s, the 16 workers ran ~2,050, and `gemm.tasks` grew by ~1,500 a second. 2 processes is the setting where the API and 16 workers (prefetch 1) match.
- **Prefetch fixed the workers.** A worker with prefetch 1 waits idle for every round trip to RabbitMQ. With prefetch N it works on N tasks at once and the waits overlap: the same 16 workers drain 2.3× faster at prefetch 10. From prefetch 2 on, `gemm.tasks` stays empty.
- **Then the results consumers were the bottleneck.** With 4 API processes and prefetch 2 or more, ~2,050 results/s were saved whatever the prefetch, and `gemm.results` grew instead. The 8 consumers used 7.3 cores, about one each: each a Python process at its limit.
- **Deriving the job status made every consumer ~57% faster.** A result is now one `UPDATE` of its own run row: no lock on the job, no loading the job and its runs. The whole system went from ~2,050 to ~3,100 tasks/s.
- **Now the machine is the limit.** On its own every part does more than 4,700 tasks/s, but together they settle at ~3,100 with 25 of 32 threads busy. Each task costs ~7.3 ms of CPU across all services, which is what this machine can supply at that rate (see section 3).
- **At 8 API processes the machine is the limit.** The API uses 7–8 cores, 25–26 of 32 threads are busy, and the workers and consumers get less done than at 4.
- **More processes means more database connections.** Each process has its own pool. 4 API processes plus 8 consumers ran Postgres out of connections at its default limit of 100; it's now 250.

## 1. Each part at its peak

### API: how many jobs it accepts

With the workers stopped, the API only accepts jobs and publishes tasks. Nothing else competes with it. 20,000 jobs from 40 load processes:

| API processes | Jobs/s | Tasks/s |
|---|---|---|
| 1 | 409 | 2,045 |
| 2 | 760 | 3,800 |
| 4 | 1,382 | 6,910 |
| 8 | 2,070 | 10,350 |

From 1 to 4 processes it scales almost evenly. 8 processes give less per process; whether that's the API or the load generator on the same machine wasn't checked. The run with 1 process matches the three earlier runs (398–424 jobs/s).

### Workers: the drain test

Stop the workers, fill `gemm.tasks` with 100,000 tasks, start N workers and measure how fast the queue empties (the slope while it drains from 80% to 20%).

| Workers | Tasks/s | Per worker | Worker CPU (all of them) |
|---|---|---|---|
| 4 | 945 | 236 | 0.7 cores |
| 8 | 1,696 | 212 | 1.6 cores |
| 16 | 2,569 | 161 | 3.6 cores |

More workers help, but each one does less: 236 → 161 tasks/s. A worker takes one task at a time and spends most of it waiting (0.23 cores each): for the next delivery, and for RabbitMQ to confirm the result is stored. Why that wait grows with more workers isn't proven yet. RabbitMQ isn't short of CPU, so the likely cause is something it does one message at a time per queue, such as writing each message to disk. The rerun with 16 workers gave 2,586 tasks/s.

### Workers: prefetch

Prefetch is how many unacked tasks RabbitMQ lets one worker hold. aio-pika runs each delivery as its own asyncio task, so a worker with prefetch N works on up to N tasks at once: while one waits for RabbitMQ's confirm, another runs. The same drain test, 16 workers:

| Prefetch | Time to empty | Tasks/s | Per worker | Worker CPU (all of them) |
|---|---|---|---|---|
| 1 | 45.9 s | ~2,180 | 136 | 3.8 cores |
| 2 | 29.8 s | ~3,350 | 209 | 5.1 cores |
| 4 | 25.4 s | ~3,940 | 246 | 5.7 cores |
| 10 | 20.1 s | ~4,970 | 311 | 6.4 cores |

These rates are 100,000 tasks divided by the time from starting the workers to an empty queue, which includes start-up and up to ~5 s of lag before the empty queue shows. So they are lower than the real rates; at prefetch 1 the slope method gave 2,570–2,590. The slope didn't work for these shorter drains: RabbitMQ's management API refreshed queue counts only every ~5 s, which left one or two points between the 80% and 20% marks.

- Prefetch 2 already gives half of the gain of 10; 4 gives about 80%.
- With live queue depths (after these runs), prefetch 4 gave a proper slope: **~5,850 tasks/s** (5,070 as total over time to empty). So the numbers in this table are low by roughly 15–25%.
- Prefetch stays 1 by default (`WORKER_PREFETCH`). With the GPU runner, kernels running side by side would slow each other down and the measured timings would be wrong. Higher values are for the fake runner.
- With prefetch N, a crashed worker sends N tasks back to the queue, and each of them uses up one of its delivery attempts. The fake runner also holds N sets of matrices in memory, which matters for large sizes.

### Results consumers: the drain test

Stop the consumers, let the workers fill `gemm.results` with 100,000 results, start N consumers and measure how fast it empties.

| Consumers | Results/s | Per consumer | Consumer CPU | Postgres CPU |
|---|---|---|---|---|
| 1 | 665 | 665 | 1.0 | 0.2 |
| 2 | 1,319 | 659 | 1.8 | 0.4 |
| 4 | 2,142 | 536 | 3.3 | 0.7 |
| 8 | 3,044 | 381 | 6.4 | 1.5 |

Up to 2 consumers scale evenly; after that each adds less. Every save locks its job's row, so the 5 results of one job wait for each other. During a load run with 8 consumers, Postgres showed up to 8 sessions waiting on that lock, plus waits on disk syncs at commit.

### Results consumers without the job lock

The job's status is no longer stored; it's derived from its runs when the job is read. A save is one `UPDATE` of the run's own row, so results of the same job don't wait for each other, and nothing loads the job or its runs. The same drain test, with live queue depths:

| Consumers | Results/s | Before | Per consumer | Consumer CPU per result | Postgres CPU |
|---|---|---|---|---|---|
| 1 | 1,050 | 665 | 1,050 | 1.32 ms | 0.6 cores |
| 2 | 2,084 | 1,319 | 1,042 | 1.32 ms | 1.3 cores |
| 4 | 3,409 | 2,142 | 852 | 1.60 ms | 2.7 cores |
| 8 | 4,743 | 3,044 | 593 | 2.15 ms | 4.2 cores |

- **+56–59% at every number of consumers.**
- **Scaling isn't more even than before:** 1 → 8 consumers is ~4.5× both times. So the gain comes mostly from cheaper saves, not from less waiting. What still makes each consumer slower as more are added is the shared machine: CPU per result rises from 1.3 to 2.15 ms.
- **Postgres works harder per result than before** (~0.6–0.9 ms against ~0.3–0.5 ms), although one `UPDATE` should be cheaper than the old lock, read and two updates. Not explained yet; table bloat from millions of benchmark rows is a candidate.

## 2. The whole system

16 workers, N consumers, and `load.py` sending `POST /jobs` as fast as it can from P processes. Each run is a 40 s window after an 8 s warm-up.

### One API process, different numbers of consumers

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

### More API processes, 8 consumers

| API processes | Load processes | Tasks/s in | Results saved/s | Peak `gemm.tasks` | Mean / p95 latency | API CPU | Busy threads (of 32) |
|---|---|---|---|---|---|---|---|
| 1 | 40 | 1,538 | 1,538 | 52 | 125 / 242 ms | 1.14 | 11 |
| 1 | 160 | 1,461 | 1,461 | 22 | 542 / 737 ms | 1.11 | 10 |
| 2 | 40 | 2,073 | 2,071 | 98 | 91 / 232 ms | 2.12 | 18 |
| 2 | 160 | 1,961 | 1,962 | 44 | 402 / 915 ms | 2.12 | 18 |
| 4 | 40 | 3,585 | 2,050 | 61,884 (growing) | 50 / 83 ms | 4.04 | 22 |
| 4 | 160 | 3,373 | 1,952 | 53,941 (growing) | 228 / 557 ms | 4.11 | 23 |
| 8 | 40 | 6,377 | 1,656 | 194,217 (growing) | 28 / 49 ms | 7.26 | 25 |
| 8 | 160 | 6,195 | 1,362 | 187,509 (growing) | 119 / 245 ms | 7.69 | 26 |

- **1 → 2 processes:** about 35% more tasks/s through the whole system, and the queues stay empty. The API is still at its limit (2.1 cores), so latency improves only a little.
- **4 processes:** the API takes in more than the workers can run. Results are saved at ~2,000/s, the workers' rate, and `gemm.tasks` grows. Latency drops, because the API has room now and requests no longer queue in front of it.
- **8 processes:** the API takes in ~6,300 tasks/s but fewer results are saved than at 4. The API's 7–8 cores take CPU from the workers and consumers on the same machine.
- At 4 and 8, the run with 160 load processes started with tasks the run with 40 had left in `gemm.tasks` (since fixed in `bench.py`). Intake isn't affected; the peak depths are.

### Worker prefetch, 4 API processes, 8 consumers

40 load processes:

| Prefetch | Tasks/s in | Results saved/s | Peak `gemm.tasks` | `gemm.results` at the end | Worker CPU | Consumer CPU | Busy threads (of 32) |
|---|---|---|---|---|---|---|---|
| 1 | 3,739 | 1,995 | 66,090 (growing) | 64 | 3.5 | 7.1 | 23 |
| 2 | 3,580 | 2,093 | 417 | 57,424 (growing) | 4.9 | 7.3 | 24 |
| 4 | 3,520 | 2,054 | 63 | 58,248 (growing) | 5.1 | 7.3 | 24 |
| 10 | 3,552 | 2,076 | 82 | 58,715 (growing) | 5.2 | 7.3 | 23 |

- With prefetch 1, tasks pile up in `gemm.tasks`: the workers are the limit.
- From prefetch 2 on, `gemm.tasks` stays empty and the pile moves to `gemm.results`: the consumers are the limit. Results saved stay at ~2,050/s, below the consumers' ~3,040/s in the drain test, because here they share the machine with the API and the workers.
- The worker drain test shows the same: with prefetch 2 or more, `gemm.results` took 40 s to empty every time (~2,500/s), however fast the workers were.

### No job lock: 4 API processes, prefetch 4, 8 consumers

40 load processes:

| Tasks/s in | Results saved/s | Peak `gemm.tasks` | Peak `gemm.results` | Mean / p95 latency | Busy threads (of 32) |
|---|---|---|---|---|---|
| 3,105 | 3,089 | 42 | 2,628 | 58 / 96 ms | 25 |

CPU per service: API 3.7, consumers 8.1, workers 4.8, RabbitMQ 1.9, Postgres 4.2 cores.

- Everything keeps up: no queue grows, and results are saved as fast as jobs arrive.
- The API accepts less than in the prefetch runs (3,105 vs ~3,550 tasks/s) with the same 4 processes. The consumers now use 8 cores instead of 7, and Postgres 4.2 instead of 2.5, so the API gets less of the machine.

## 3. The bottleneck

| | Tasks/s |
|---|---|
| API alone, 1 / 2 / 4 processes | ~2,050 / ~3,800 / ~6,900 |
| 16 workers alone, prefetch 1 / 4 / 10 | ~2,570 / ~3,940 / ~4,970 |
| 4 / 8 consumers alone | ~2,140 / ~3,040 |
| **Whole system, 1 API process** | **1,400–1,700** |
| **Whole system, 2 API processes** | **~2,000** |
| **Whole system, 4 API processes, prefetch 1** | **~2,000 saved, ~3,700 accepted; `gemm.tasks` grows** |
| **Whole system, 4 API processes, prefetch 2–10** | **~2,050 saved, ~3,550 accepted; `gemm.results` grows** |
| API alone, 4 processes (rerun) / 16 workers alone, prefetch 4 / 8 consumers alone, no job lock | ~6,590 / ~5,850 / ~4,740 |
| **Whole system, no job lock** | **~3,100, queues stay small** |

With one process, the API has the lowest peak and is the part running flat out while everything else has room. It's a single Python process, and Python runs one thread's code at a time, so that process can't use more than about one core. The whole system runs below even the API's own peak (1,400–1,700 vs ~2,050), because the API slows down when the rest is busy. That gap is the open question in section 2.

With 2 or more processes, the API's peak (~3,800) is above the workers' (~2,570), and the whole system settles at ~2,000 tasks/s: what the 16 workers manage while sharing the machine with everything else. The bottleneck has moved to the workers. On a single machine, more workers only help while there are free cores; at 8 API processes there are hardly any left.

With prefetch 2 or more, the workers' peak was above what 4 API processes send, and the whole system still saved only ~2,050 results/s. The pile was in `gemm.results`, so the results consumers were the bottleneck. Each one ran flat out at about one core, and each save also waited on its job's row lock and a disk sync.

Without the job lock, every part on its own is above 4,700 tasks/s and the whole system runs at ~3,100 with no queue growing. No single part is the bottleneck; the machine is.

### CPU budget per task

CPU per task in the whole-system run without the job lock (cores ÷ 3,089 tasks/s):

| Part | CPU per task |
|---|---|
| Results consumers | 2.6 ms |
| Workers | 1.55 ms |
| Postgres | 1.36 ms |
| API | 1.19 ms |
| RabbitMQ | 0.62 ms |
| **Total** | **~7.3 ms** |

The 32 threads are 16 cores with SMT. Two threads on one core get roughly 1.2–1.3 cores of work done, not 2, so the machine supplies about 20 cores' worth. 20 cores ÷ ~7 ms per task ≈ 2,800–3,200 tasks/s, which is where the whole system sits. To go further, a task has to cost less CPU (the consumers and Postgres first, they cost the most), or the services have to spread over more machines.

## 4. The database

After a day of benchmarks (16 Nov 2026, before purging it):

| Table | Rows | Table size | Indexes |
|---|---|---|---|
| `results` | 8.6 M | 1.77 GB | 0.94 GB |
| `jobs` | 1.7 M | 151 MB | 44 MB |

- **99.9% of it was benchmark data:** 1,719,483 of 1,721,706 jobs were fake-runner jobs of 64³ or smaller.
- **About 1.7 KB per job:** one `jobs` row and five `results` rows, with their indexes. At the ~620 jobs/s of the whole-system run that's ~1 MB/s: **~3.6 GB an hour, ~90 GB a day.** A real deployment needs a retention policy, e.g. partitioning `results` and `jobs` by day or month and dropping old partitions whole.
- **A redundant index:** `ix_results_job_id` (195 MB) duplicates the unique index on `(job_id, kernel)`, which starts with `job_id` and serves the same lookups.
- **Only 37% of the updates to `results` were HOT.** A HOT ("heap-only tuple") update writes the new row version on the same page and touches no index. It needs free space on that page. Each run is inserted as queued and updated once when its result arrives; with the default fillfactor of 100 the page is usually full by then, so the new version goes to another page and all three indexes get a new entry. A fillfactor of ~80–85 on `results` leaves room for that one update.
- **Postgres runs on its defaults:** `shared_buffers` 128 MB against 2.7 GB of `results` and its indexes, and `max_wal_size` 1 GB, which makes checkpoints frequent at this write rate (after each one, the first change to a page logs the whole 8 KB page). `pg_stat_statements` isn't enabled, so the cost of each query isn't visible yet.
- **The benchmarks ran on a table that kept growing.** The morning's "before" numbers ran on a much smaller table than the night's "after" numbers. That may be part of why Postgres's CPU per result went up after the job lock was removed; not checked.

The database was then purged (2.9 GB → 8 MB; the 2,223 jobs that weren't benchmarks were exported first). From now on, benchmarks start from an empty database.

## History

**Before: job status stored, one lock per job** (16 Nov 2026, night; 4 API processes, 16 workers, 8 consumers):

| | Job lock | Status derived from the runs |
|---|---|---|
| 1 / 8 consumers alone | 665 / 3,044 results/s | 1,050 / 4,743 results/s |
| Whole system | ~2,050 saved/s, consumers are the limit | ~3,100 saved/s, the machine is the limit |

**Before: worker prefetch 1** (16 Nov 2026, evening; 4 API processes, 16 workers, 8 consumers):

| | Prefetch 1 | Prefetch 2 / 4 / 10 |
|---|---|---|
| Workers alone (drain) | ~2,180 tasks/s | ~3,350 / ~3,940 / ~4,970 tasks/s |
| Whole system | ~2,000 saved/s, workers are the limit | ~2,050 saved/s, results consumers are the limit |

**Before: one API process** (16 Nov 2026, afternoon; 16 workers, 8 consumers):

| | 1 process | 2 processes | 4 processes |
|---|---|---|---|
| API alone | ~410 jobs/s | ~760 jobs/s | ~1,380 jobs/s |
| Whole system | ~300 jobs/s, API is the limit | ~400 jobs/s, queues empty | ~700 jobs/s accepted, workers are the limit |

**Before: the results consumer ran inside the API process** (16 Nov 2026, morning; 8 workers, 1 consumer):

| | Before | After |
|---|---|---|
| API intake under load | ~200 jobs/s | 285–340 jobs/s (with 4+ consumers) |
| Results saved under load | ~290/s, backlog grew ~700/s | keeps up with 4+ consumers |
| Results consumer on its own | ~630/s, could not scale | 665/s each; 8 do ~3,040/s |

Taking jobs and saving results shared one process and one core, so saving results halved how fast the API accepted jobs (430 jobs/s with no results to save, 200 with them). Moving the consumer into its own service raised API intake by 40–70% and made the consumers scalable.

## How it was measured

```sh
make up RUNNER=fake WORKERS=16 RESULTS=8 API_PROCESSES=4 PREFETCH=4
uv run python scripts/bench.py api 40 160      # whole system, per number of load processes
uv run python scripts/bench.py worker          # API fill rate, then worker drain (uses the running workers)
uv run python scripts/bench.py results         # consumer drain (uses the running consumers)
```

Scale between runs with `make api API_PROCESSES=N`, `make worker WORKERS=N RUNNER=fake PREFETCH=N` and `make results RESULTS=N`.

- **Throughput:** jobs accepted from the API's `/metrics`; results saved by counting rows in Postgres; drain rates from the slope of the queue depth (from the 80% to the 20% mark).
- **Latency:** from the API's request histogram. The mean is exact; p95 is estimated from the histogram buckets.
- **CPU:** per service from `podman stats` (replicas added up); the whole machine from `/proc/stat`.
- **Queue depths:** live, from a passive `queue.declare` over AMQP every 0.5 s (under 1 ms per read). Earlier runs read RabbitMQ's management API, which refreshes about every 5 s; for the prefetch runs that was too coarse and they report total over time to empty instead.
- **Caveats:**
  - The load generator runs on the same machine as everything it tests.
  - Each load process waits for its answer before sending the next request, so the load never exceeds the number of processes.
  - Each run was done once.
  - Until 16 Nov 2026 the database was never reset between runs, so later runs worked on bigger tables (up to 8.6 M runs). Since then benchmarks start from an empty database.
  - The "before" numbers of the results consumer split were measured with the `rabbitmqctl` polling described above.
