from prometheus_client import Counter, Histogram

# Default registry: Prometheus scrapes these from GET /metrics.

HTTP_REQUESTS = Counter("api_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_SECONDS = Histogram("api_http_request_seconds", "HTTP request duration", ["method", "route"])
JOBS_SUBMITTED = Counter("api_jobs_submitted_total", "Jobs accepted by POST /jobs")
TASK_PUBLISH_FAILURES = Counter(
    "api_task_publish_failures_total", "Jobs saved whose tasks failed to publish"
)
RESULTS_SAVED = Counter(
    "api_results_saved_total", "Run results written to the DB", ["kernel", "status"]
)
JOB_SECONDS = Histogram(
    "api_job_seconds",
    "Submit to finish, per job",
    # Fine steps up to a minute (where queueing delay shows), coarse after.
    buckets=(0.5, 1, 2, 3, 5, 7.5, 10, 15, 20, 25, 30, 45, 60, 90, 120, 300, 600, 1800),
)
