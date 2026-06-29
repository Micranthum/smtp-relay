"""
Prometheus metrics for the SMTP relay.

Multiprocess mode: set PROMETHEUS_MULTIPROC_DIR before starting any process.
prometheus_client detects it at import time and writes per-process .db files
to that directory. The HTTP server (relay process only) aggregates them via
MultiProcessCollector. The RQ worker writes metrics to files but does not
run an HTTP server.
"""
import os
import logging
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
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
    'Total emails accepted into queue',
    ['from_ip'],
)

emails_sent = Counter(
    'smtp_relay_emails_sent_total',
    'Total emails successfully delivered to Graph API',
)

emails_failed = Counter(
    'smtp_relay_emails_failed_total',
    'Total emails that failed after exhausting all retries',
    ['reason'],
)

emails_retried = Counter(
    'smtp_relay_emails_retried_total',
    'Total retry attempts on Graph API failures',
)

graph_api_duration = Histogram(
    'smtp_relay_graph_api_duration_seconds',
    'Graph API sendMail POST request duration',
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

tls_failures = Counter(
    'smtp_relay_tls_failures_total',
    'TLS handshake failures caused by scanner bot STARTTLS probes',
)

queue_depth = Gauge(
    'smtp_relay_queue_depth',
    'Number of email jobs currently queued in Redis',
)


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

    start_http_server(port, registry=registry)
    logger.info(f'Prometheus metrics server started on :{port}/metrics')
