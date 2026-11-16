from prometheus_client import Counter, Histogram

# Default registry: Prometheus scrapes these from GET /metrics.

HTTP_REQUESTS = Counter("api_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_SECONDS = Histogram("api_http_request_seconds", "HTTP request duration", ["method", "route"])
JOBS_SUBMITTED = Counter("api_jobs_submitted_total", "Jobs accepted by POST /jobs")
TASK_PUBLISH_FAILURES = Counter(
    "api_task_publish_failures_total", "Jobs saved whose tasks failed to publish"
)
