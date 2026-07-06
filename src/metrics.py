"""
Prometheus metrics for the SMTP relay.

Multiprocess mode: set PROMETHEUS_MULTIPROC_DIR before starting any process.
prometheus_client detects it at import time and writes per-process .db files
to that directory. The HTTP server (relay process only) aggregates them via
MultiProcessCollector. The RQ worker writes metrics to files but does not
run an HTTP server.

queue_depth is intentionally NOT a multiprocess Gauge — it is exposed via a
custom Collector that reads the RQ queue count from Redis on each scrape,
giving an accurate real-time value without per-process file accumulation.
"""
import os
import logging
from prometheus_client import (
    Counter,
    Histogram,
    CollectorRegistry,
    REGISTRY,
    start_http_server,
)
from prometheus_client.core import GaugeMetricFamily

logger = logging.getLogger('smtp_relay')

_metrics_server_started = False

# ---------------------------------------------------------------------------
# Metric definitions
# ---------------------------------------------------------------------------

emails_received = Counter(
    'smtp_relay_emails_received_total',
    'Emails accepted by the SMTP server and enqueued to RQ (before delivery attempt)',
    ['from_ip'],
)

emails_sent = Counter(
    'smtp_relay_emails_sent_total',
    'Emails successfully delivered to Microsoft 365 via Graph API (HTTP 202)',
)

emails_failed = Counter(
    'smtp_relay_emails_failed_total',
    'Emails permanently failed after exhausting all RQ retries; reason=exception class name',
    ['reason'],
)

emails_retried = Counter(
    'smtp_relay_emails_retried_total',
    'RQ retry attempts scheduled after a transient delivery failure',
)

graph_api_duration = Histogram(
    'smtp_relay_graph_api_duration_seconds',
    'Round-trip duration of the Graph API POST /sendMail request',
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

tls_failures = Counter(
    'smtp_relay_tls_failures_total',
    'TLS handshake failures (typically scanner/bot probes, not real clients)',
)

ip_rejected = Counter(
    'smtp_relay_ip_rejected_total',
    'Connections hard-rejected at connection_made() because the peer IP is not in ALLOWED_IPS '
    '(closed before the 220 greeting, before any SMTP command is processed)',
)


# ---------------------------------------------------------------------------
# Real-time queue depth — custom collector, reads Redis on each scrape
# ---------------------------------------------------------------------------

class _QueueDepthCollector:
    """
    Reads the RQ 'email' queue length from Redis on every Prometheus scrape.
    Avoids multiprocess Gauge pitfalls (multiple processes writing the same
    gauge get summed, giving wildly incorrect values).
    """
    def __init__(self, redis_url: str, queue_name: str):
        self._redis_url = redis_url
        self._queue_name = queue_name

    def collect(self):
        from redis import Redis
        from rq import Queue
        try:
            conn = Redis.from_url(self._redis_url, socket_connect_timeout=1)
            depth = float(Queue(self._queue_name, connection=conn).count)
        except Exception:
            depth = -1.0  # -1 signals Redis is unreachable at scrape time
        g = GaugeMetricFamily(
            'smtp_relay_queue_depth',
            'Current number of email jobs waiting in the RQ queue (read from Redis at scrape time)',
        )
        g.add_metric([], depth)
        yield g


# ---------------------------------------------------------------------------
# Metrics HTTP server
# ---------------------------------------------------------------------------

def start_metrics_server(port: int, redis_url: str, queue_name: str) -> None:
    """
    Start the Prometheus HTTP server in a daemon thread.
    Only the relay process calls this.
    In multiprocess mode the serving registry is a fresh CollectorRegistry
    fed by MultiProcessCollector (aggregates all per-process .db files).
    """
    global _metrics_server_started
    if _metrics_server_started:
        return
    _metrics_server_started = True

    multiproc_dir = os.environ.get('PROMETHEUS_MULTIPROC_DIR')

    if multiproc_dir:
        try:
            from prometheus_client import multiprocess
            os.makedirs(multiproc_dir, exist_ok=True)
            registry = CollectorRegistry()
            multiprocess.MultiProcessCollector(registry)
            logger.info(f'Prometheus: multiprocess mode (dir={multiproc_dir})')
        except Exception as exc:
            logger.warning(f'Prometheus: multiprocess init failed ({exc}), using single-process mode')
            registry = REGISTRY
    else:
        registry = REGISTRY
        logger.info('Prometheus: single-process mode (PROMETHEUS_MULTIPROC_DIR not set)')

    registry.register(_QueueDepthCollector(redis_url, queue_name))
    start_http_server(port, registry=registry)
    logger.info(f'Prometheus metrics server started on :{port}/metrics')
