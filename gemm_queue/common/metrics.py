import asyncio
import logging

from prometheus_client import CollectorRegistry, push_to_gateway

logger = logging.getLogger(__name__)


def push(url: str, job: str, instance: str, registry: CollectorRegistry) -> None:
    """Push a registry to the Pushgateway, one group per instance (so replicas stay apart).

    Does nothing without a URL. A failed push is logged, never raised: metrics
    must not break the work they describe.
    """
    if not url:
        return
    try:
        push_to_gateway(
            url,
            job=job,
            registry=registry,
            grouping_key={"instance": instance},
            timeout=3,
        )
    except OSError as exc:
        logger.warning("pushing %s metrics to %s failed: %s", job, url, exc)


async def push_forever(
    url: str, job: str, instance: str, registry: CollectorRegistry, interval_s: float
) -> None:
    """Push every interval_s, for long-running services."""
    while True:
        await asyncio.to_thread(push, url, job, instance, registry)
        await asyncio.sleep(interval_s)
