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

There is no automated test suite (no pytest, no unittest runner).

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
                → MS365OAuth (MSAL, token cached in Redis)
                → Graph API POST sendMail
                    → on_send_success / on_send_failure callbacks
Prometheus HTTP (port 8000, /metrics)
    → Prometheus server (scrapes smtp-relay:8000, monitoring/prometheus.yml)
        → Alertmanager (config rendered from .env at startup, sends alerts to Telegram)
```

**Two separate processes share one Docker image:**
- `smtp-relay` container: runs `src/main.py` (SMTP server + metrics HTTP server)
- `worker` container: runs `python -m src.worker` (RQ worker, no HTTP listener)

Both mount a shared `prometheus-multiproc` volume. Prometheus metrics are aggregated from both processes via `MultiProcessCollector` when `PROMETHEUS_MULTIPROC_DIR` is set.

## Module responsibilities

| File | Role |
|---|---|
| `src/main.py` | Wires up two `aiosmtpd` controllers and the metrics server; handles signals |
| `src/relay.py` | SMTP handlers (`SMTPRelayHandler`, auth, rate limiting, RQ enqueue) |
| `src/worker.py` | RQ job function `send_email_job`, Graph API call, job callbacks, worker `main()` |
| `src/oauth.py` | MSAL `ConfidentialClientApplication` wrapper; token cached in Redis (`SETEX`, TTL-based) |
| `src/config.py` | All env-var reads; `Config.validate()` called at startup by both processes |
| `src/metrics.py` | Prometheus counter/histogram/gauge definitions; `start_metrics_server()` |
| `src/logger.py` | Rotating file + console logger named `smtp_relay` |
| `monitoring/prometheus.yml` | Scrape config (`smtp-relay:8000`) + alerting config; not read by any `src/` code |
| `monitoring/alert_rules.yml` | Alert rules (permanent failures, retry rate, queue backlog, target/Redis down) |
| `monitoring/render-alertmanager-config.sh` | Alertmanager's entrypoint: renders `alertmanager.yml` from `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` (via `env_file: .env`) at container startup, then execs Alertmanager |

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

## Monitoring stack (Prometheus + Alertmanager)

`docker compose up -d` also starts `prometheus` (port `9090`, TSDB in
the `prometheus-data` volume, retention via `PROMETHEUS_RETENTION_TIME`) and
`alertmanager` (port `9093`). Both are published on all interfaces (`0.0.0.0`),
reachable from the LAN — neither has built-in authentication, so this relies
entirely on the network perimeter/firewall to keep them off the public
internet. If that's ever not sufficient, bind them back to `127.0.0.1` in
`docker-compose.yml` and access via SSH tunnel, or put a reverse proxy with
auth in front.

Alertmanager has no native env-var substitution in its config file, so
`monitoring/render-alertmanager-config.sh` (mounted as its entrypoint) writes
`/etc/alertmanager/alertmanager.yml` from `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`
(read via `env_file: .env`) before `exec`-ing the real binary. Set those two
in `.env` — get a bot token from `@BotFather` on Telegram, and `chat_id` from
the destination chat/group (negative number for groups).

Alerts are delivered via Telegram (a direct outbound HTTPS call to
`api.telegram.org`), not through the relay itself — this sidesteps the
"relay is down, can't send its own alert" problem that an email-based
receiver would have.
