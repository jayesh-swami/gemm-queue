from prometheus_client import CollectorRegistry, Counter, Gauge

# Own registry: only these are pushed, not the default process metrics.
REGISTRY = CollectorRegistry()

REPUBLISHED = Counter(
    "sweeper_republished_total", "Stuck runs whose task was re-published", registry=REGISTRY
)
FAILED = Counter(
    "sweeper_failed_total", "Runs marked failed after running out of attempts", registry=REGISTRY
)
LAST_SUCCESS = Gauge(
    "sweeper_last_success_timestamp_seconds", "When the last pass finished", registry=REGISTRY
)
