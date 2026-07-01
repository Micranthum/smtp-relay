"""
Mass Email Load Test for SMTP Relay
Measures SMTP acceptance rate and waits for actual delivery via Prometheus metrics.
"""

import smtplib
import time
import threading
import sys
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import requests

SMTP_SERVER = "localhost"
USE_TLS     = False
USERNAME    = "yourusername"
PASSWORD    = "yourpassword"
FROM_EMAIL  = "sender@example.com"
METRICS_URL = "http://localhost:8000/metrics"


class Colors:
    GREEN   = '\033[92m'
    RED     = '\033[91m'
    YELLOW  = '\033[93m'
    CYAN    = '\033[96m'
    RESET   = '\033[0m'
    BOLD    = '\033[1m'


stats = {
    'total': 0,
    'success': 0,
    'failed': 0,
    'rate_limited': 0,
    'connection_errors': 0,
    'auth_errors': 0,
    'timeout_errors': 0,
    'smtp_errors': defaultdict(int),
    'start_time': None,
    'end_time': None,
    'response_times': [],
}
stats_lock = threading.Lock()
sent_emails = []
sent_emails_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Prometheus helpers
# ---------------------------------------------------------------------------

def _parse_metrics(text: str) -> dict:
    """
    Parse Prometheus text format into {metric_name: total_value}.
    Sums across all label combinations for the same base metric name.
    Ignores histogram buckets (_bucket suffix) and _created suffixes.
    """
    result = {}
    for line in text.splitlines():
        if line.startswith('#') or not line.strip():
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        name_labels = parts[0]
        try:
            value = float(parts[1])
        except ValueError:
            continue
        name = name_labels.split('{')[0]
        if name.endswith('_bucket') or name.endswith('_created'):
            continue
        result[name] = result.get(name, 0.0) + value
    return result


def get_metrics(url: str) -> tuple:
    """Returns (metrics_dict, error_string)."""
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        return _parse_metrics(r.text), None
    except Exception as exc:
        return {}, str(exc)


# ---------------------------------------------------------------------------
# Email generation and sending
# ---------------------------------------------------------------------------

def generate_test_email(index: int) -> tuple:
    unique_id  = f"test{index:05d}-{int(time.time())}"
    test_email = f"{unique_id}@mailinator.com"
    return test_email, unique_id


def send_single_email(email_number: int, use_tls: bool, port: int, timeout: int) -> dict:
    start_time            = time.time()
    to_email, unique_id   = generate_test_email(email_number)

    result = {
        'number':        email_number,
        'success':       False,
        'to':            to_email,
        'unique_id':     unique_id,
        'response_time': 0.0,
        'error':         None,
        'timestamp':     datetime.now().isoformat(),
    }

    try:
        msg            = MIMEMultipart('alternative')
        msg['From']    = FROM_EMAIL
        msg['To']      = to_email
        msg['Subject'] = f"Test #{email_number:05d} - SMTP Relay Load Test"

        text_body = (
            f"TEST EMAIL #{email_number:05d}\n"
            f"Unique ID : {unique_id}\n"
            f"Timestamp : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Recipient : {to_email}\n"
            f"Verify at : https://www.mailinator.com/v4/public/inboxes.jsp?to={unique_id}\n"
        )
        html_body = f"""<html><body>
<h2>Test #{email_number:05d}</h2>
<p><b>Unique ID:</b> {unique_id}</p>
<p><b>Recipient:</b> {to_email}</p>
<p><b>Timestamp:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
<p><a href="https://www.mailinator.com/v4/public/inboxes.jsp?to={unique_id}">View in Mailinator</a></p>
</body></html>"""

        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))

        if use_tls and port == 465:
            smtp = smtplib.SMTP_SSL(SMTP_SERVER, port, timeout=timeout)
        elif use_tls and port == 587:
            smtp = smtplib.SMTP(SMTP_SERVER, port, timeout=timeout)
            smtp.starttls()
        else:
            smtp = smtplib.SMTP(SMTP_SERVER, port, timeout=timeout)

        smtp.login(USERNAME, PASSWORD)
        smtp.send_message(msg)
        smtp.quit()

        result['success']       = True
        result['response_time'] = time.time() - start_time

        with stats_lock:
            stats['success'] += 1
            stats['response_times'].append(result['response_time'])

        with sent_emails_lock:
            sent_emails.append({
                'number':    email_number,
                'to':        to_email,
                'unique_id': unique_id,
            })

    except smtplib.SMTPAuthenticationError as e:
        result['error'] = f"Auth error: {e}"
        with stats_lock:
            stats['auth_errors'] += 1
            stats['failed'] += 1
            stats['smtp_errors']['auth'] += 1

    except smtplib.SMTPServerDisconnected as e:
        result['error'] = f"Server disconnected: {e}"
        with stats_lock:
            stats['connection_errors'] += 1
            stats['failed'] += 1
            stats['smtp_errors']['disconnected'] += 1

    except TimeoutError as e:
        result['error'] = f"Timeout: {e}"
        with stats_lock:
            stats['timeout_errors'] += 1
            stats['failed'] += 1
            stats['smtp_errors']['timeout'] += 1

    except smtplib.SMTPException as e:
        msg_lower = str(e).lower()
        if any(w in msg_lower for w in ('rate', 'limit', 'too many', 'throttl', '451')):
            result['error'] = f"Rate limited: {e}"
            with stats_lock:
                stats['rate_limited'] += 1
                stats['failed'] += 1
                stats['smtp_errors']['rate_limit'] += 1
        else:
            result['error'] = f"SMTP error: {e}"
            with stats_lock:
                stats['failed'] += 1
                stats['smtp_errors']['smtp_general'] += 1

    except Exception as e:
        result['error'] = f"Unknown: {type(e).__name__}: {e}"
        with stats_lock:
            stats['failed'] += 1
            stats['smtp_errors']['unknown'] += 1

    result['response_time'] = time.time() - start_time
    return result


# ---------------------------------------------------------------------------
# Progress bar
# ---------------------------------------------------------------------------

def print_progress_bar(current: int, total: int, start_time: float, bar_length: int = 50):
    elapsed  = time.time() - start_time
    rate     = current / elapsed if elapsed > 0 else 0
    eta      = (total - current) / rate if rate > 0 else 0
    filled   = int(bar_length * current / total)
    bar      = '█' * filled + '░' * (bar_length - filled)
    sys.stdout.write(
        f'\r{Colors.CYAN}[{bar}] {current/total*100:5.1f}% '
        f'({current}/{total}) | '
        f'OK {stats["success"]} FAIL {stats["failed"]} | '
        f'{rate:.1f}/s | ETA: {eta:.0f}s{Colors.RESET}'
    )
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Delivery verification via Prometheus
# ---------------------------------------------------------------------------

def wait_for_delivery(
    baseline: dict,
    expected: int,
    metrics_url: str,
    timeout_seconds: int,
    poll_interval: int = 5,
) -> dict:
    """
    Poll Prometheus metrics until `expected` emails have been delivered+failed
    (i.e. they have left the queue), or until timeout_seconds elapses.

    Returns a summary dict.
    """
    SENT_KEY   = 'smtp_relay_emails_sent_total'
    FAILED_KEY = 'smtp_relay_emails_failed_total'
    DEPTH_KEY  = 'smtp_relay_queue_depth'

    baseline_sent   = baseline.get(SENT_KEY, 0.0)
    baseline_failed = baseline.get(FAILED_KEY, 0.0)

    deadline    = time.time() + timeout_seconds
    start       = time.time()
    last_sent   = 0
    last_failed = 0
    last_depth  = expected

    print(f"\n{Colors.CYAN}Waiting for delivery via Graph API "
          f"(timeout: {timeout_seconds}s)...{Colors.RESET}")
    print(f"{'Elapsed':>8}  {'Delivered':>10}  {'Failed':>8}  {'Pending':>8}  {'Rate':>10}")
    print('-' * 55)

    while time.time() < deadline:
        m, err = get_metrics(metrics_url)
        if err:
            print(f"\r{Colors.YELLOW}Metrics unavailable: {err}{Colors.RESET}", end='')
            time.sleep(poll_interval)
            continue

        sent_delta   = m.get(SENT_KEY, 0.0)   - baseline_sent
        failed_delta = m.get(FAILED_KEY, 0.0) - baseline_failed
        depth        = m.get(DEPTH_KEY, 0.0)
        resolved     = sent_delta + failed_delta
        pending      = max(0, expected - resolved)
        elapsed      = time.time() - start

        # Delivery rate (emails/min) based on recent delta
        interval_sent = sent_delta - last_sent
        rate_per_min  = (interval_sent / poll_interval) * 60

        print(
            f"\r{elapsed:>7.0f}s  "
            f"{Colors.GREEN}{sent_delta:>10.0f}{Colors.RESET}  "
            f"{Colors.RED}{failed_delta:>8.0f}{Colors.RESET}  "
            f"{Colors.YELLOW}{pending:>8.0f}{Colors.RESET}  "
            f"{rate_per_min:>8.1f}/min",
            end='  ',
        )
        sys.stdout.flush()

        last_sent   = sent_delta
        last_failed = failed_delta
        last_depth  = depth

        if pending == 0 and resolved >= expected:
            print(f"\n{Colors.GREEN}All {expected} emails resolved.{Colors.RESET}")
            break

        time.sleep(poll_interval)
    else:
        print(f"\n{Colors.YELLOW}Timeout reached after {timeout_seconds}s. "
              f"Some emails may still be in retry queue.{Colors.RESET}")

    m, _ = get_metrics(metrics_url)
    sent_delta   = m.get(SENT_KEY, 0.0)   - baseline_sent
    failed_delta = m.get(FAILED_KEY, 0.0) - baseline_failed
    elapsed      = time.time() - start

    return {
        'delivered':     int(sent_delta),
        'failed':        int(failed_delta),
        'pending':       max(0, expected - int(sent_delta) - int(failed_delta)),
        'elapsed':       elapsed,
        'timed_out':     time.time() >= deadline,
        'rate_per_min':  (sent_delta / elapsed) * 60 if elapsed > 0 else 0,
    }


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(delivery: dict | None, total_smtp: int):
    smtp_time = stats['end_time'] - stats['start_time']

    print("\n\n" + "=" * 80)
    print(f"{Colors.BOLD}{Colors.CYAN}LOAD TEST SUMMARY{Colors.RESET}")
    print("=" * 80)

    # --- SMTP acceptance phase ---
    print(f"\n{Colors.BOLD}Phase 1 — SMTP Acceptance (queuing speed){Colors.RESET}")
    print(f"  Accepted into queue : {Colors.GREEN}{stats['success']}{Colors.RESET} / {stats['total']}")
    print(f"  Rejected            : {Colors.RED}{stats['failed']}{Colors.RESET}")
    if stats['rate_limited']:
        print(f"  Rate-limited (451)  : {Colors.RED}{stats['rate_limited']}{Colors.RESET}")
    print(f"  Total time          : {smtp_time:.2f}s")
    print(f"  Acceptance rate     : {stats['total']/smtp_time:.0f} emails/sec  "
          f"{Colors.YELLOW}← this is queuing speed, not delivery speed{Colors.RESET}")

    if stats['response_times']:
        avg = sum(stats['response_times']) / len(stats['response_times'])
        print(f"  SMTP latency        : avg {avg*1000:.0f}ms  "
              f"min {min(stats['response_times'])*1000:.0f}ms  "
              f"max {max(stats['response_times'])*1000:.0f}ms")

    if stats['failed'] > 0:
        print(f"\n  {Colors.BOLD}SMTP errors:{Colors.RESET}")
        for k, v in sorted(stats['smtp_errors'].items(), key=lambda x: -x[1]):
            print(f"    {k}: {v}")

    # --- Delivery phase ---
    print(f"\n{Colors.BOLD}Phase 2 — Actual Delivery (Graph API → Microsoft 365){Colors.RESET}")
    if delivery is None:
        print(f"  {Colors.YELLOW}Skipped (use --verify to enable){Colors.RESET}")
    else:
        total_d   = delivery['delivered'] + delivery['failed'] + delivery['pending']
        delivered = delivery['delivered']
        failed    = delivery['failed']
        pending   = delivery['pending']
        elapsed   = delivery['elapsed']
        rate      = delivery['rate_per_min']

        pct = lambda n: f"{n/total_smtp*100:.1f}%" if total_smtp else "n/a"

        print(f"  Delivered           : {Colors.GREEN}{delivered}{Colors.RESET}  ({pct(delivered)})")
        print(f"  Permanently failed  : {Colors.RED}{failed}{Colors.RESET}  ({pct(failed)})")
        if pending:
            print(f"  Still pending       : {Colors.YELLOW}{pending}{Colors.RESET}  "
                  f"(in retry queue or in-flight)")
        print(f"  Time to deliver     : {elapsed:.0f}s")
        print(f"  Delivery rate       : {rate:.1f} emails/min  "
              f"{Colors.YELLOW}← actual throughput through Graph API{Colors.RESET}")
        if delivery['timed_out']:
            print(f"  {Colors.YELLOW}Verification timed out — increase --verify-timeout if needed{Colors.RESET}")

    # --- Manual verification links ---
    if sent_emails:
        print(f"\n{Colors.BOLD}Manual verification (first 5 Mailinator inboxes):{Colors.RESET}")
        for e in sent_emails[:5]:
            url = f"https://www.mailinator.com/v4/public/inboxes.jsp?to={e['unique_id']}"
            print(f"  {e['to']}")
            print(f"    {Colors.CYAN}{url}{Colors.RESET}")

    print("\n" + "=" * 80 + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Load test for SMTP Relay — measures acceptance and real delivery.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --emails 100 --threads 5
  %(prog)s --emails 100 --threads 5 --verify --verify-timeout 300
  %(prog)s --emails 50 --port 465 --tls --verify
        """,
    )
    parser.add_argument('--emails',          type=int, default=100,  help='Emails to send (default: 100)')
    parser.add_argument('--threads',         type=int, default=5,    help='Concurrent SMTP connections (default: 5)')
    parser.add_argument('--port',            type=int, default=None, help='SMTP port (auto: 465 TLS / 587 plain)')
    parser.add_argument('--tls',             action='store_true',    help='Enable TLS/SSL')
    parser.add_argument('--timeout',         type=int, default=30,   help='SMTP connection timeout in seconds')
    parser.add_argument('--verify',          action='store_true',    help='Wait for actual delivery via Prometheus')
    parser.add_argument('--verify-timeout',  type=int, default=300,  help='Max seconds to wait for delivery (default: 300)')
    parser.add_argument('--metrics-url',     default=METRICS_URL,    help=f'Prometheus metrics URL (default: {METRICS_URL})')
    parser.add_argument('--no-confirm',      action='store_true',    help='Skip the ENTER confirmation prompt')
    args = parser.parse_args()

    use_tls = args.tls or USE_TLS
    port    = args.port or (465 if use_tls else 587)

    if use_tls:
        mode_desc = "SSL/TLS port 465" if port == 465 else "STARTTLS port 587"
    else:
        mode_desc = f"Plain SMTP port {port} (no encryption)"

    stats['total'] = args.emails

    print("\n" + "=" * 80)
    print(f"{Colors.BOLD}{Colors.CYAN}SMTP RELAY LOAD TEST{Colors.RESET}")
    print("=" * 80)
    print(f"\n{Colors.BOLD}Configuration:{Colors.RESET}")
    print(f"  Server      : {SMTP_SERVER}:{port}  ({mode_desc})")
    print(f"  From        : {FROM_EMAIL}")
    print(f"  Emails      : {args.emails}")
    print(f"  Threads     : {args.threads}")
    print(f"  User        : {USERNAME}")
    print(f"  Recipients  : @mailinator.com  (verify at mailinator.com)")
    if args.verify:
        print(f"  Verify via  : {args.metrics_url}  (timeout: {args.verify_timeout}s)")

    if not use_tls:
        print(f"\n{Colors.YELLOW}WARNING: TLS disabled — development mode only.{Colors.RESET}")

    # --- Read baseline metrics before sending ---
    baseline = {}
    if args.verify:
        baseline, err = get_metrics(args.metrics_url)
        if err:
            print(f"\n{Colors.YELLOW}Cannot reach metrics endpoint: {err}{Colors.RESET}")
            print("Delivery verification will be skipped.")
            args.verify = False
        else:
            b_sent   = baseline.get('smtp_relay_emails_sent_total', 0)
            b_failed = baseline.get('smtp_relay_emails_failed_total', 0)
            b_rcvd   = baseline.get('smtp_relay_emails_received_total', 0)
            print(f"\n  Baseline metrics:")
            print(f"    Received so far : {b_rcvd:.0f}")
            print(f"    Sent so far     : {b_sent:.0f}")
            print(f"    Failed so far   : {b_failed:.0f}")

    if not args.no_confirm:
        try:
            input(f"\n{Colors.BOLD}Press ENTER to start...{Colors.RESET} ")
        except EOFError:
            print(f"\n{Colors.YELLOW}(non-interactive shell — starting automatically){Colors.RESET}")

    # --- Phase 1: Send ---
    print(f"\n{Colors.CYAN}Sending {args.emails} emails...{Colors.RESET}\n")
    stats['start_time'] = time.time()

    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        futures = {
            executor.submit(send_single_email, i, use_tls, port, args.timeout): i
            for i in range(1, args.emails + 1)
        }
        completed = 0
        for future in as_completed(futures):
            completed += 1
            try:
                future.result()
            except Exception as e:
                print(f"\n{Colors.RED}Unexpected error: {e}{Colors.RESET}")
            print_progress_bar(completed, args.emails, stats['start_time'])

    stats['end_time'] = time.time()
    print()

    # --- Phase 2: Wait for delivery ---
    delivery = None
    if args.verify and stats['success'] > 0:
        delivery = wait_for_delivery(
            baseline        = baseline,
            expected        = stats['success'],
            metrics_url     = args.metrics_url,
            timeout_seconds = args.verify_timeout,
        )

    print_summary(delivery, stats['total'])


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Interrupted.{Colors.RESET}\n")
        sys.exit(1)
    except Exception as e:
        import traceback
        print(f"\n{Colors.RED}Fatal: {e}{Colors.RESET}\n")
        traceback.print_exc()
        sys.exit(1)
