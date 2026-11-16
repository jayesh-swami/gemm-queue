"""Measure the API, results consumer and workers under load. Results in docs/load-tests.md.

uv run python scripts/bench.py api 10 20 40 80   # load.py flat out at each process count
uv run python scripts/bench.py worker            # time the workers emptying a full gemm.tasks

Expects the stack up (make up) with fake workers. Prints one JSON line per run.

api:    per process count, an 8 s warm-up, then a 40 s window. Then the load stops
        and the time for gemm.results to empty is measured (the consumer alone).
worker: stop the workers, queue 20,000 jobs, start the workers, time the drain.
"""

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["podman", "compose", "-f", "deploy/docker-compose.yml", "--project-directory", "."]
POST = 'method="POST",route="/jobs"'


def metrics() -> dict[str, float]:
    """The API's /metrics as {series: value}."""
    text = urllib.request.urlopen("http://localhost:8000/metrics").read().decode()
    out = {}
    for line in text.splitlines():
        if line and not line.startswith("#"):
            name, value = line.rsplit(" ", 1)
            out[name] = float(value)
    return out


def total(m: dict[str, float], name: str) -> float:
    """Sum of a metric over all its labels."""
    return sum(v for k, v in m.items() if k == name or k.startswith(name + "{"))


def post_histogram(m: dict[str, float]) -> tuple[list[tuple[float, float]], float, float]:
    """POST /jobs latency: (cumulative buckets, count, sum)."""
    buckets = []
    for k, v in m.items():
        if k.startswith("api_http_request_seconds_bucket{") and POST in k:
            le = re.search(r'le="([^"]+)"', k).group(1)
            buckets.append((float(le), v))  # float("+Inf") is inf
    buckets.sort()
    count = m.get(f"api_http_request_seconds_count{{{POST}}}", 0.0)
    seconds = m.get(f"api_http_request_seconds_sum{{{POST}}}", 0.0)
    return buckets, count, seconds


def quantile(q: float, before, after) -> float:
    """Like Prometheus' histogram_quantile, over what changed between two snapshots."""
    deltas = [(le, c1 - c0) for (le, c1), (_, c0) in zip(after[0], before[0], strict=True)]
    rank = q * deltas[-1][1]
    prev_le, prev_c = 0.0, 0.0
    for le, c in deltas:
        if c >= rank:
            if le == float("inf"):
                return prev_le
            return prev_le + (le - prev_le) * (rank - prev_c) / max(c - prev_c, 1e-9)
        prev_le, prev_c = le, c
    return float("nan")


def depths() -> dict[str, int]:
    """Messages per queue. RabbitMQ refreshes these every few seconds for quorum queues."""
    out = subprocess.run(
        [
            "podman",
            "exec",
            "gemm-queue-mq-1",
            "rabbitmqctl",
            "-q",
            "list_queues",
            "-p",
            "/",
            "name",
            "messages",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return {name: int(n) for name, n in (line.split() for line in out.splitlines()[1:])}


class Sampler(threading.Thread):
    """Records queue depths every 0.5 s, to report peaks."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.samples: list[tuple[float, dict[str, int]]] = []
        self.running = True

    def run(self) -> None:
        while self.running:
            self.samples.append((time.time(), depths()))
            time.sleep(0.5)

    def peak(self, queue: str, start: float, end: float) -> int:
        return max((d.get(queue, 0) for t, d in self.samples if start <= t <= end), default=0)


def wait_empty(queue: str, timeout: float = 900) -> float:
    start = time.time()
    while time.time() - start < timeout:
        if depths().get(queue, 0) == 0:
            return time.time()
        time.sleep(0.5)
    raise TimeoutError(f"{queue} not empty after {timeout} s")


def start_load(procs: int, jobs: int) -> subprocess.Popen:
    return subprocess.Popen(
        [
            "uv",
            "run",
            "python",
            "scripts/load.py",
            "--jobs",
            str(jobs),
            "--size",
            "64",
            "--every",
            "0",
            "--procs",
            str(procs),
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # its own process group, so stop_load reaches the children
    )


def stop_load(load: subprocess.Popen) -> None:
    if load.poll() is None:
        os.killpg(load.pid, signal.SIGTERM)
    load.wait()


def compose(*args: str) -> None:
    subprocess.run(COMPOSE + list(args), cwd=ROOT, check=True, capture_output=True)


def emit(**fields) -> None:
    print(json.dumps(fields), flush=True)


def bench_api(procs_list: list[int], warmup: float = 8, window: float = 40) -> None:
    sampler = Sampler()
    sampler.start()
    for procs in procs_list:
        wait_empty("gemm.results")
        time.sleep(5)
        load = start_load(procs, jobs=100_000)  # more than the window needs
        time.sleep(warmup)
        t0, m0 = time.time(), metrics()
        time.sleep(window)
        t1, m1 = time.time(), metrics()
        stop_load(load)
        t_stop = time.time()

        # Load stopped: only the results consumer is busy now.
        backlog = depths().get("gemm.results", 0)
        d0, md0 = time.time(), metrics()
        d1 = wait_empty("gemm.results")
        md1 = metrics()

        dt, drain = t1 - t0, d1 - d0
        h0, h1 = post_histogram(m0), post_histogram(m1)
        jobs = total(m1, "api_jobs_submitted_total") - total(m0, "api_jobs_submitted_total")
        saved = total(m1, "api_results_saved_total") - total(m0, "api_results_saved_total")
        drained = total(md1, "api_results_saved_total") - total(md0, "api_results_saved_total")
        emit(
            bench="api",
            procs=procs,
            jobs_per_s=round(jobs / dt, 1),
            tasks_per_s=round(5 * jobs / dt, 1),
            post_mean_ms=round(1000 * (h1[2] - h0[2]) / max(h1[1] - h0[1], 1), 1),
            post_p50_ms=round(1000 * quantile(0.5, h0, h1), 1),
            post_p95_ms=round(1000 * quantile(0.95, h0, h1), 1),
            post_p99_ms=round(1000 * quantile(0.99, h0, h1), 1),
            api_cpu_cores=round(
                (m1["process_cpu_seconds_total"] - m0["process_cpu_seconds_total"]) / dt, 2
            ),
            results_saved_per_s=round(saved / dt, 1),
            peak_tasks_depth=sampler.peak("gemm.tasks", t0, t1),
            results_backlog_at_stop=backlog,
            peak_results_depth=sampler.peak("gemm.results", t0, t_stop),
            drain_s=round(drain, 1),
            drain_results_per_s=round(drained / drain, 1),
            drain_api_cpu_cores=round(
                (md1["process_cpu_seconds_total"] - md0["process_cpu_seconds_total"]) / drain, 2
            ),
        )
    sampler.running = False


def bench_worker(procs: int = 40, jobs_per_proc: int = 500) -> None:
    wait_empty("gemm.results")
    compose("stop", "worker")
    t_fill, m0 = time.time(), metrics()
    start_load(procs, jobs_per_proc).wait()
    fill = time.time() - t_fill
    jobs = total(metrics(), "api_jobs_submitted_total") - total(m0, "api_jobs_submitted_total")
    tasks = 5 * int(jobs)  # the queue depth lags, the counter doesn't

    sampler = Sampler()
    sampler.start()
    t0 = time.time()
    compose("start", "worker")
    tasks_empty = wait_empty("gemm.tasks")
    results_empty = wait_empty("gemm.results")
    sampler.running = False
    emit(
        bench="worker",
        jobs=int(jobs),
        tasks=tasks,
        fill_s=round(fill, 1),
        fill_jobs_per_s=round(jobs / fill, 1),  # API with no results to save
        tasks_drain_s=round(tasks_empty - t0, 1),
        worker_tasks_per_s=round(tasks / (tasks_empty - t0), 1),
        peak_results_depth=sampler.peak("gemm.results", t0, results_empty),
        results_done_s=round(results_empty - t0, 1),
    )


if __name__ == "__main__":
    if sys.argv[1:2] == ["api"]:
        bench_api([int(p) for p in sys.argv[2:]] or [10, 20, 40, 80])
    elif sys.argv[1:2] == ["worker"]:
        bench_worker()
    else:
        sys.exit(__doc__)
