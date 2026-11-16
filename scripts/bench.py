"""Measure the API, results consumer and workers under load. Results in docs/load-tests.md.

uv run python scripts/bench.py api 10 20 40 80   # load.py flat out at each process count
uv run python scripts/bench.py worker            # time the workers emptying a full gemm.tasks
uv run python scripts/bench.py results           # time the results consumers emptying gemm.results

Expects the stack up (make up) with fake workers. Prints one JSON line per run.

api:    per process count, an 8 s warm-up, then a 40 s window. Then the load stops
        and the time for gemm.results to empty is measured (the consumers alone).
worker: stop the workers, queue 20,000 jobs, start the workers, time the drain.
results: stop the results consumers, let the workers fill gemm.results with 100,000
         results, start the consumers, time the drain.
"""

import base64
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

from gemm_queue.api.settings import settings

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["podman", "compose", "-f", "deploy/docker-compose.yml", "--project-directory", "."]
POST = 'method="POST",route="/jobs"'


def metrics(url: str = "http://localhost:8000/metrics") -> dict[str, float]:
    """A /metrics page (the API's by default) as {series: value}."""
    text = urllib.request.urlopen(url).read().decode()
    out = {}
    for line in text.splitlines():
        if line and not line.startswith("#"):
            name, value = line.rsplit(" ", 1)
            out[name] = float(value)
    return out


def total(m: dict[str, float], name: str, job: str = "") -> float:
    """Sum of a metric over all its labels, optionally only one Pushgateway job."""
    return sum(
        v
        for k, v in m.items()
        if (k == name or k.startswith(name + "{")) and (not job or f'job="{job}"' in k)
    )


def container_cpu() -> dict[str, float]:
    """CPU seconds used so far per compose service, replicas added up."""
    stats = json.loads(
        subprocess.run(
            ["podman", "stats", "--no-stream", "--format", "json"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    cpu: dict[str, float] = {}
    for c in stats:
        if m := re.fullmatch(r"gemm-queue-(.+)-\d+", c["name"]):
            cpu[m[1]] = cpu.get(m[1], 0.0) + go_duration(c["cpu_time"])
    return cpu


def go_duration(text: str) -> float:
    """'1h2m3.5s' -> seconds."""
    units = {"h": 3600, "m": 60, "s": 1, "ms": 1e-3, "us": 1e-6, "µs": 1e-6, "ns": 1e-9}
    return sum(float(n) * units[u] for n, u in re.findall(r"([\d.]+)(h|ms|us|µs|ns|m|s)", text))


def host_cpu() -> float:
    """Busy CPU seconds of the whole machine (all cores), from /proc/stat."""
    with open("/proc/stat") as f:
        fields = [int(x) for x in f.readline().split()[1:9]]  # up to steal; guest is in user
    idle = fields[3] + fields[4]  # idle + iowait
    return (sum(fields) - idle) / os.sysconf("SC_CLK_TCK")


def cores(before: dict[str, float], after: dict[str, float], seconds: float) -> dict[str, float]:
    """CPU cores used per service between two container_cpu() snapshots."""
    return {
        k: round((after[k] - before.get(k, 0.0)) / seconds, 2)
        for k in ("api", "results", "worker", "mq", "db")
        if k in after
    }


def saved_total() -> int:
    """Runs with a saved result. Exact, unlike the pushed counters."""
    return int(psql("SELECT count(*) FROM results WHERE status <> 'QUEUED'"))


def psql(query: str) -> str:
    return subprocess.run(
        [
            "podman",
            "exec",
            "gemm-queue-db-1",
            "sh",
            "-c",
            f'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "{query}"',
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def replicas(service: str) -> int:
    out = subprocess.run(
        ["podman", "ps", "--filter", f"name=gemm-queue-{service}-", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return len(out.split())


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
    """Messages per queue, from the management API. RabbitMQ refreshes these every few
    seconds. (Not rabbitmqctl: each call starts an Erlang VM inside the broker's
    container and costs it several cores when polled twice a second.)"""
    request = urllib.request.Request("http://localhost:15672/api/queues/%2F?columns=name,messages")
    auth = f"{settings.rabbitmq_user}:{settings.rabbitmq_password}".encode()
    request.add_header("Authorization", "Basic " + base64.b64encode(auth).decode())
    with urllib.request.urlopen(request, timeout=5) as response:
        return {q["name"]: q.get("messages", 0) for q in json.load(response)}


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
        wait_empty("gemm.tasks")  # a run can leave tasks behind when the API outpaces the workers
        wait_empty("gemm.results")
        time.sleep(5)
        load = start_load(procs, jobs=100_000)  # more than the window needs
        time.sleep(warmup)
        t0, m0, s0, c0, h0 = time.time(), metrics(), saved_total(), container_cpu(), host_cpu()
        time.sleep(window)
        t1, m1, s1, c1, h1 = time.time(), metrics(), saved_total(), container_cpu(), host_cpu()
        stop_load(load)
        t_stop = time.time()

        # Load stopped: only the results consumer is busy now.
        backlog = depths().get("gemm.results", 0)
        d0, ds0, dc0 = time.time(), saved_total(), container_cpu()
        d1 = wait_empty("gemm.results")
        ds1, dc1 = saved_total(), container_cpu()

        dt, drain = t1 - t0, d1 - d0
        p0, p1 = post_histogram(m0), post_histogram(m1)
        jobs = total(m1, "api_jobs_submitted_total") - total(m0, "api_jobs_submitted_total")
        emit(
            bench="api",
            procs=procs,
            workers=replicas("worker"),
            results_consumers=replicas("results"),
            jobs_per_s=round(jobs / dt, 1),
            tasks_per_s=round(5 * jobs / dt, 1),
            post_mean_ms=round(1000 * (p1[2] - p0[2]) / max(p1[1] - p0[1], 1), 1),
            post_p50_ms=round(1000 * quantile(0.5, p0, p1), 1),
            post_p95_ms=round(1000 * quantile(0.95, p0, p1), 1),
            post_p99_ms=round(1000 * quantile(0.99, p0, p1), 1),
            results_saved_per_s=round((s1 - s0) / dt, 1),
            cpu_cores=cores(c0, c1, dt),
            host_busy_cores=round((h1 - h0) / dt, 1),
            peak_tasks_depth=sampler.peak("gemm.tasks", t0, t1),
            results_backlog_at_stop=backlog,
            peak_results_depth=sampler.peak("gemm.results", t0, t_stop),
            drain_s=round(drain, 1),
            drain_results_per_s=round((ds1 - ds0) / drain, 1),
            drain_cpu_cores=cores(dc0, dc1, drain),
        )
    sampler.running = False


def bench_worker(procs: int = 40, jobs_per_proc: int = 500) -> None:
    wait_empty("gemm.tasks")  # only this run's tasks, or the drain rate is wrong
    wait_empty("gemm.results")
    compose("stop", "worker")
    t_fill, m0 = time.time(), metrics()
    start_load(procs, jobs_per_proc).wait()
    fill = time.time() - t_fill
    jobs = total(metrics(), "api_jobs_submitted_total") - total(m0, "api_jobs_submitted_total")
    tasks = 5 * int(jobs)  # the queue depth lags, the counter doesn't

    sampler = Sampler()
    sampler.start()
    t0, c0, h0 = time.time(), container_cpu(), host_cpu()
    compose("start", "worker")
    tasks_empty = wait_empty("gemm.tasks")
    c1, h1 = container_cpu(), host_cpu()
    results_empty = wait_empty("gemm.results")
    sampler.running = False
    emit(
        bench="worker",
        workers=replicas("worker"),
        results_consumers=replicas("results"),
        jobs=int(jobs),
        tasks=tasks,
        fill_s=round(fill, 1),
        fill_jobs_per_s=round(jobs / fill, 1),  # API with no results to save
        tasks_drain_s=round(tasks_empty - t0, 1),
        worker_tasks_per_s=round(tasks / (tasks_empty - t0), 1),
        # From the slope of the queue depth: not skewed by the depth's lag or by start-up.
        worker_tasks_per_s_steady=round(
            drain_slope(sampler, "gemm.tasks", tasks, t0, tasks_empty), 1
        ),
        cpu_cores=cores(c0, c1, tasks_empty - t0),
        host_busy_cores=round((h1 - h0) / (tasks_empty - t0), 1),
        peak_results_depth=sampler.peak("gemm.results", t0, results_empty),
        results_done_s=round(results_empty - t0, 1),
    )


def bench_results(procs: int = 40, jobs_per_proc: int = 500) -> None:
    wait_empty("gemm.tasks")
    wait_empty("gemm.results")
    compose("stop", "results")
    m0 = metrics()
    start_load(procs, jobs_per_proc).wait()
    jobs = total(metrics(), "api_jobs_submitted_total") - total(m0, "api_jobs_submitted_total")
    results = 5 * int(jobs)
    wait_empty("gemm.tasks")
    while depths().get("gemm.results", 0) < results:  # the depth lags; wait for all of them
        time.sleep(1)

    sampler = Sampler()
    sampler.start()
    t0, s0, c0 = time.time(), saved_total(), container_cpu()
    compose("start", "results")
    results_empty = wait_empty("gemm.results")
    s1, c1 = saved_total(), container_cpu()
    sampler.running = False
    emit(
        bench="results",
        workers=replicas("worker"),
        results_consumers=replicas("results"),
        results=results,
        drain_s=round(results_empty - t0, 1),
        saved_per_s=round((s1 - s0) / (results_empty - t0), 1),
        saved_per_s_steady=round(
            drain_slope(sampler, "gemm.results", results, t0, results_empty), 1
        ),
        cpu_cores=cores(c0, c1, results_empty - t0),
    )


def drain_slope(sampler: Sampler, queue: str, full: int, start: float, end: float) -> float:
    """Messages/s while queue drained from 80% to 20% full (least-squares slope)."""
    points = [
        (t, d[queue])
        for t, d in sampler.samples
        if start <= t <= end and 0.2 * full < d.get(queue, 0) < 0.8 * full
    ]
    n = len(points)
    mean_t = sum(t for t, _ in points) / n
    mean_d = sum(d for _, d in points) / n
    slope = sum((t - mean_t) * (d - mean_d) for t, d in points) / sum(
        (t - mean_t) ** 2 for t, _ in points
    )
    return -slope


if __name__ == "__main__":
    if sys.argv[1:2] == ["api"]:
        bench_api([int(p) for p in sys.argv[2:]] or [10, 20, 40, 80])
    elif sys.argv[1:2] == ["worker"]:
        bench_worker()
    elif sys.argv[1:2] == ["results"]:
        bench_results()
    else:
        sys.exit(__doc__)
