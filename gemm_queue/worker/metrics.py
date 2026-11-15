from prometheus_client import CollectorRegistry, Counter, Histogram

# Own registry: only these are pushed, not the default process metrics.
REGISTRY = CollectorRegistry()
PUSH_INTERVAL_S = 5

TASKS = Counter(
    "worker_tasks_total",
    "Tasks handled. outcome: passed, wrong_result, kernel_failed or error (sent back to the queue)",
    ["kernel", "outcome"],
    registry=REGISTRY,
)
TASK_SECONDS = Histogram(
    "worker_task_seconds",
    "Wall time per task: make inputs, run, verify, publish",
    ["kernel"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
    registry=REGISTRY,
)
KERNEL_SECONDS = Histogram(
    "worker_kernel_seconds",
    "Kernel time per run, as reported by the runner",
    ["kernel"],
    buckets=(0.0005, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 5),
    registry=REGISTRY,
)
