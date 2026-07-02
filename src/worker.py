"""
RQ worker entry point and email delivery job.

Entry point: python -m src.worker
"""
import base64
import time
import requests
from email.parser import BytesParser
from email.policy import default
from email.utils import parseaddr
from redis import Redis
from rq import Queue, Worker
from rq.job import Retry, get_current_job
from requests.exceptions import ConnectionError as RequestsConnectionError, Timeout

from .config import Config
from .logger import logger
from .oauth import MS365OAuth
from .metrics import emails_sent, emails_failed, emails_retried, graph_api_duration

# Per-worker-process OAuth singleton — avoids re-reading the token cache file
# and re-acquiring MSAL state on every job.
_oauth = None


def _get_oauth() -> MS365OAuth:
    global _oauth
    if _oauth is None:
        _oauth = MS365OAuth()
    return _oauth


# ---------------------------------------------------------------------------
# RQ job callbacks — run in the PARENT worker process, so Prometheus
# multiprocess counters accumulate correctly (unlike the forked job child).
# ---------------------------------------------------------------------------

def on_send_success(job, connection, result, *args, **kwargs) -> None:
    emails_sent.inc()
    logger.info(f'Job {job.id}: email delivered successfully')


def on_send_failure(job, connection, type, value, traceback, *args, **kwargs) -> None:
    # RQ 1.16 calls on_failure on EVERY failure, not just the final one.
    # Check retries_left (still pre-decrement at this point) to distinguish.
    reason = type.__name__ if type else 'unknown'
    if job.retries_left:
        # Will be retried — log as transient, don't count as permanent failure.
        logger.warning(
            f'Job {job.id}: transient failure ({reason}), '
            f'{job.retries_left} retry(ies) left: {value}'
        )
    else:
        # retries_left == 0 or None: no more retries, this is the final failure.
        emails_failed.labels(reason=reason).inc()
        logger.error(f'Job {job.id}: email permanently failed ({reason}): {value}')


# ---------------------------------------------------------------------------
# Custom worker — tracks retry attempts in the parent process where
# Prometheus multiprocess metrics work reliably.
# ---------------------------------------------------------------------------

class SMTPRelayWorker(Worker):
    def handle_job_failure(self, job, queue, started_job_registry=None, exc_string=''):
        # retries_left is still > 0 here when a retry is about to be scheduled.
        if job.retries_left and job.retries_left > 0:
            emails_retried.inc()
            logger.info(
                f'Job {job.id}: scheduling retry '
                f'({job.retries_left} attempt(s) left)'
            )
        super().handle_job_failure(
            job,
            queue,
            started_job_registry=started_job_registry,
            exc_string=exc_string,
        )


# ---------------------------------------------------------------------------
# Graph API message builder
# ---------------------------------------------------------------------------

def _build_graph_message(msg, rcpt_tos: list) -> dict:
    subject = msg.get('Subject', 'No Subject')

    to_recipients = []
    for recipient in rcpt_tos:
        _, email_addr = parseaddr(recipient)
        to_recipients.append({
            'emailAddress': {'address': email_addr if email_addr else recipient}
        })

    graph_msg = {
        'subject': subject,
        'from': {'emailAddress': {'address': Config.MS365_EMAIL_ADDRESS}},
        'toRecipients': to_recipients,
    }

    if msg.is_multipart():
        html_body = None
        text_body = None
        attachments = []

        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get('Content-Disposition', ''))

            if content_type == 'text/plain' and 'attachment' not in content_disposition:
                text_body = part.get_content()
            elif content_type == 'text/html' and 'attachment' not in content_disposition:
                html_body = part.get_content()
            elif 'attachment' in content_disposition or part.get_filename():
                filename = part.get_filename() or 'attachment'
                payload_bytes = part.get_payload(decode=True)
                if payload_bytes:
                    attachments.append({
                        '@odata.type': '#microsoft.graph.fileAttachment',
                        'name': filename,
                        'contentType': content_type,
                        'contentBytes': base64.b64encode(payload_bytes).decode('utf-8'),
                    })

        if html_body:
            graph_msg['body'] = {'contentType': 'HTML', 'content': html_body}
        elif text_body:
            graph_msg['body'] = {'contentType': 'Text', 'content': text_body}

        if attachments:
            graph_msg['attachments'] = attachments
            logger.debug(f'Including {len(attachments)} attachment(s)')
    else:
        body = msg.get_content()
        content_type = msg.get_content_type()
        graph_msg['body'] = {
            'contentType': 'HTML' if content_type == 'text/html' else 'Text',
            'content': body,
        }

    return graph_msg


# ---------------------------------------------------------------------------
# RQ job function
# ---------------------------------------------------------------------------

def send_email_job(content_b64: str, mail_from: str, rcpt_tos: list) -> dict:
    """
    Deliver one email via the Microsoft Graph API sendMail endpoint.
    Called by the RQ worker. Retried automatically by RQ on exception.

    content_b64: base64.b64encode(envelope.content).decode('utf-8')
    """
    content_bytes = base64.b64decode(content_b64.encode('utf-8'))
    msg = BytesParser(policy=default).parsebytes(content_bytes)
    graph_message = _build_graph_message(msg, rcpt_tos)

    oauth = _get_oauth()
    token = oauth.get_access_token()

    graph_url = f'{oauth.graph_endpoint}/users/{Config.MS365_EMAIL_ADDRESS}/sendMail'
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }
    payload = {'message': graph_message, 'saveToSentItems': 'true'}

    logger.info(f'Sending email from {mail_from} to {rcpt_tos} via Graph API')

    t0 = time.monotonic()
    try:
        response = requests.post(graph_url, headers=headers, json=payload, timeout=30)
    except (RequestsConnectionError, Timeout) as exc:
        job = get_current_job()
        retries_left = job.retries_left if job else 'unknown'
        logger.warning(
            f'Network error sending to {rcpt_tos} (retries_left={retries_left}): {exc}'
        )
        raise
    graph_api_duration.observe(time.monotonic() - t0)

    if response.status_code == 202:
        logger.info(f'Graph API accepted email to {rcpt_tos} (HTTP 202)')
        return {'status': 'sent', 'recipients': rcpt_tos}

    error_msg = f'Graph API error {response.status_code}: {response.text[:200]}'

    if response.status_code in (400, 403):
        # Permanent errors — exhaust retries so on_failure fires immediately.
        job = get_current_job()
        if job:
            job.retries_left = 0
            job.save()
        logger.error(f'Permanent Graph API error, will not retry: {error_msg}')
    else:
        job = get_current_job()
        retries_left = job.retries_left if job else 'unknown'
        logger.warning(f'Transient Graph API error (retries_left={retries_left}): {error_msg}')

    raise Exception(error_msg)


# ---------------------------------------------------------------------------
# Worker entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Start the RQ worker. Invoked via: python -m src.worker"""
    import os

    multiproc_dir = os.environ.get('PROMETHEUS_MULTIPROC_DIR')
    if multiproc_dir:
        os.makedirs(multiproc_dir, exist_ok=True)

    Config.validate(check_tls=False)

    logger.info('=' * 60)
    logger.info('SMTP Relay Worker — RQ email delivery')
    logger.info('=' * 60)
    logger.info(f'Redis URL : {Config.REDIS_URL}')
    logger.info(f'Queue     : email')
    logger.info(f'Retries   : {Config.RQ_MAX_RETRIES} at {Config.RQ_RETRY_INTERVALS}s')

    # Pre-register known failure reasons at 0 so Prometheus has a baseline
    # sample before the first real failure — a Counter label that "appears"
    # already at 1 (never having been 0) makes increase() blind to that
    # first occurrence, since there's no prior sample to diff against.
    for reason in ('Exception', 'ConnectionError', 'Timeout'):
        emails_failed.labels(reason=reason)

    redis_conn = Redis.from_url(Config.REDIS_URL)
    queue = Queue('email', connection=redis_conn, default_timeout=120)
    worker = SMTPRelayWorker([queue], connection=redis_conn)

    logger.info('Worker ready, waiting for jobs')
    worker.work(with_scheduler=True)


if __name__ == '__main__':
    main()
