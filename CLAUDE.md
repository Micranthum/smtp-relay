# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

An SMTP relay that accepts emails from legacy applications using Basic Auth (LOGIN/PLAIN SASL) and delivers them to Microsoft 365 via the Graph API (`POST /users/{email}/sendMail`). It decouples reception from delivery using Redis + RQ: the SMTP process enqueues jobs immediately and returns `250 OK`, while a separate worker process handles OAuth2 token management and Graph API calls with retry logic.

## Running the stack

```bash
# Start all services (redis, smtp-relay, worker)
docker compose up -d

# Rebuild after code changes
docker compose build --no-cache && docker compose up -d

# View logs
docker compose logs -f smtp-relay
docker compose logs -f worker

# Run the worker directly (outside Docker, for local dev)
python -m src.worker

# Run the SMTP server directly (outside Docker, for local dev)
python -m src.main
```

## Testing

Test scripts require manual configuration at the top of each file (server, port, credentials).

```bash
# Send a single test email with PDF attachment
python test/test_email.py

# Send bulk emails
python test/test_mass_email.py
```

There is no automated test suite (no pytest, no unittest runner). The `test/test_celery_config.py` file is a leftover from when the project used Celery — it no longer applies.

## Key environment variables

Copy `.env.example` to `.env`. Required secrets (everything else has a default):

| Variable | Purpose |
|---|---|
| `SMTP_RELAY_USERNAME` / `SMTP_RELAY_PASSWORD` | Credentials clients send to authenticate |
| `GRAPH_API_TENANT_ID` / `CLIENT_ID` / `CLIENT_SECRET` | Entra ID app credentials |
| `MS365_EMAIL_ADDRESS` | The M365 mailbox used as sender |

TLS is **forced on** when `ENVIRONMENT=production`; the env var `SMTP_RELAY_USE_TLS` is ignored in that context.

## Architecture

```
SMTP client (port 587 STARTTLS / port 465 SSL)
    → SMTPRelayHandler (aiosmtpd, async)
        → RateLimiter (per-sender, sliding window)
        → Redis Queue "email"
            → RQ Worker (src/worker.py, separate process)
                → MS365OAuth (MSAL token cache in token_cache/)
                → Graph API POST sendMail
                    → on_send_success / on_send_failure callbacks
Prometheus HTTP (port 8000, /metrics)
```

**Two separate processes share one Docker image:**
- `smtp-relay` container: runs `src/main.py` (SMTP server + metrics HTTP server)
- `worker` container: runs `python -m src.worker` (RQ worker, no HTTP listener)

Both mount `./token_cache` and a shared `prometheus-multiproc` volume. Prometheus metrics are aggregated from both processes via `MultiProcessCollector` when `PROMETHEUS_MULTIPROC_DIR` is set.

## Module responsibilities

| File | Role |
|---|---|
| `src/main.py` | Wires up two `aiosmtpd` controllers and the metrics server; handles signals |
| `src/relay.py` | SMTP handlers (`SMTPRelayHandler`, auth, rate limiting, RQ enqueue) |
| `src/worker.py` | RQ job function `send_email_job`, Graph API call, job callbacks, worker `main()` |
| `src/oauth.py` | MSAL `ConfidentialClientApplication` wrapper; file-backed token cache |
| `src/config.py` | All env-var reads; `Config.validate()` called at startup by both processes |
| `src/metrics.py` | Prometheus counter/histogram/gauge definitions; `start_metrics_server()` |
| `src/logger.py` | Rotating file + console logger named `smtp_relay` |

## Important behaviours

- **Auth is handled in the controller, not the handler.** `AuthenticatedSMTPController` and `SSLSMTPController` both implement `_authenticate()` (duplicated). The `SMTPRelayHandler` itself has no auth logic — it only checks IP/sender whitelists and rate limits in `handle_RCPT`/`handle_DATA`.
- **Email content is base64-encoded for RQ transport.** `relay.py` encodes `envelope.content` before enqueue; `worker.py` decodes and parses with `BytesParser`.
- **OAuth singleton per worker process.** `_oauth` in `worker.py` is a module-level singleton initialised lazily on the first job, reused for all subsequent jobs in the same process.
- **TLS scanner noise is suppressed.** `handle_exception` in `SMTPRelayHandler` catches `TLSSetupException` at DEBUG level; a `logging.Filter` on `mail.log` also catches any that bypass it.
- **RQ retry intervals:** default `60,300,900` seconds (1 min, 5 min, 15 min) for up to 3 retries. Configured via `RQ_RETRY_INTERVALS` (comma-separated).

## Prometheus metrics exposed

| Metric | Type | Labels |
|---|---|---|
| `smtp_relay_emails_received_total` | Counter | `from_ip` |
| `smtp_relay_emails_sent_total` | Counter | — |
| `smtp_relay_emails_failed_total` | Counter | `reason` |
| `smtp_relay_emails_retried_total` | Counter | — |
| `smtp_relay_graph_api_duration_seconds` | Histogram | — |
| `smtp_relay_tls_failures_total` | Counter | — |
| `smtp_relay_queue_depth` | Gauge | — |
