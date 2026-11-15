from prometheus_client import CollectorRegistry, Counter

from gemm_queue.common.metrics import push


def registry() -> CollectorRegistry:
    reg = CollectorRegistry()
    Counter("x_total", "test counter", registry=reg).inc()
    return reg


def test_no_url_means_no_push():
    push("", "worker", "worker-1", registry())  # returns without trying to connect


def test_unreachable_gateway_is_logged_not_raised(caplog):
    push("127.0.0.1:1", "worker", "worker-1", registry())  # nothing listens on port 1
    assert "pushing worker metrics to 127.0.0.1:1 failed" in caplog.text
