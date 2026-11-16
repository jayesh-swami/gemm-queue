from prometheus_client import CollectorRegistry, Counter, Histogram, ProcessCollector

# Own registry, pushed to the Pushgateway once per replica.
REGISTRY = CollectorRegistry()
PUSH_INTERVAL_S = 5

# CPU and memory of this process: shows whether a replica is CPU-bound.
ProcessCollector(registry=REGISTRY)

RESULTS_SAVED = Counter(
    "results_saved_total", "Run results written to the DB", ["kernel", "status"], registry=REGISTRY
)
JOB_SECONDS = Histogram(
    "results_job_seconds",
    "Submit to finish, per job",
    # Fine steps up to a minute (where queueing delay shows), coarse after.
    buckets=(0.5, 1, 2, 3, 5, 7.5, 10, 15, 20, 25, 30, 45, 60, 90, 120, 300, 600, 1800),
    registry=REGISTRY,
)
