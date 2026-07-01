# SMTP Relay - Basic Auth to Microsoft 365 OAuth2

A production-ready SMTP relay server that bridges legacy applications using Basic Authentication with Microsoft 365's modern OAuth2 authentication via Microsoft Graph API. Features asynchronous email processing with a Redis + RQ job queue, rate limiting, automatic retries, and a Prometheus/Alertmanager monitoring stack.

## Overview

This SMTP relay server enables legacy applications that only support basic SMTP authentication to send emails through Microsoft 365 accounts, which require OAuth2 authentication. The relay acts as an intermediary: it accepts basic auth credentials, enqueues the email to Redis, and returns `250 OK` immediately. A separate RQ worker process picks up the job, acquires an OAuth2 token, and delivers the email via Microsoft Graph API.

## Key Features

### Asynchronous Email Processing
- Redis + RQ job queue decouples SMTP reception from delivery
- Automatic retries on transient failures (configurable intervals, default `60,300,900`s)
- Job persistence in Redis and recovery on worker restart

### Rate Limiting
- Incoming email rate limiting (configurable, per-sender sliding window)
- No outbound throttling toward Graph API — transient errors (429/5xx/network) rely on RQ's retry intervals rather than proactive rate limiting

### Monitoring and Observability
- Prometheus metrics (`/metrics` on port 8000): emails received/sent/failed/retried, Graph API latency, TLS failures, live queue depth
- Prometheus server + Alertmanager (`monitoring/`) for historical queries and alerting
- Alerts delivered to Telegram (independent of the relay itself — keeps working even if the relay is down)
- Rotating file + console logging

## Architecture

### Core Components

```
smtp-relay/
├── src/                          # Core application source code
│   ├── __init__.py
│   ├── main.py                   # Application entry point and SMTP server setup
│   ├── relay.py                  # SMTP handlers, auth, rate limiting, RQ enqueue
│   ├── worker.py                 # RQ job function, Graph API call, job callbacks, worker main()
│   ├── oauth.py                  # Microsoft OAuth2 authentication handler
│   ├── config.py                 # Configuration management
│   ├── metrics.py                # Prometheus metric definitions and HTTP server
│   └── logger.py                 # Logging configuration
├── monitoring/                   # Prometheus + Alertmanager configuration
│   ├── prometheus.yml            # Scrape config + alerting config
│   ├── alert_rules.yml           # Alert rules
│   └── render-alertmanager-config.sh  # Renders alertmanager.yml from .env at container start
├── scripts/                      # Startup scripts
│   ├── entrypoint.sh              # Docker container entrypoint (permissions)
│   └── start.sh                  # SMTP server startup script
├── test/                         # Manual test scripts
├── certs/                        # TLS/SSL certificates (production)
├── logs/                         # Application logs
├── token_cache/                  # OAuth2 token cache
├── docker-compose.yml            # Docker compose with all services
├── Dockerfile                    # Docker image definition
└── requirements.txt               # Python dependencies
```

### System Architecture

```
┌─────────────────┐
│  Email Client   │
│ (Legacy/Modern) │
└────────┬────────┘
         │ SMTP (587 STARTTLS / 465 SSL)
         ▼
┌─────────────────────────────┐
│   SMTP Relay Server         │
│   - Rate limiting (incoming)│
│   - Auth (Basic/LOGIN/PLAIN)│
│   - Enqueue to Redis (RQ)   │
└────────┬────────────────────┘
         │
         ▼
    ┌────────┐
    │ Redis  │ Job queue "email"
    └───┬────┘
        │
        ▼
┌──────────────────────────┐
│   RQ Worker              │
│   - Retry on failure     │
│   - OAuth2 token mgmt    │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│ Microsoft Graph API      │
│ (Exchange Online)        │
└──────────────────────────┘

      Monitoring:
┌──────────────┐    ┌──────────────┐    ┌──────────┐
│  Prometheus  │───▶│ Alertmanager │───▶│ Telegram │
│ (port 9090)  │    │ (port 9093)  │    └──────────┘
└──────────────┘    └──────────────┘
```

### Module Descriptions

#### src/main.py
Main application entry point. Initializes and starts dual SMTP servers:
- Port 587: STARTTLS server (optional encryption in development, mandatory in production)
- Port 465: SSL/TLS server (implicit encryption when TLS is enabled)

Also starts the Prometheus metrics HTTP server. Validates configuration, creates TLS contexts, and manages server lifecycle/signals.

#### src/relay.py
SMTP protocol handlers. Contains:
- `SMTPRelayHandler`: handles SMTP commands, checks IP/sender whitelists and rate limits, enqueues accepted emails to RQ
- `RateLimiter`: sliding-window rate limiting for incoming emails
- `AuthenticatedSMTPController` / `SSLSMTPController`: implement authentication for the STARTTLS and implicit-SSL servers respectively (auth lives here, not in the handler)

#### src/worker.py
RQ worker entry point (`python -m src.worker`). Contains:
- `send_email_job`: builds the Graph API message, acquires an OAuth token, and POSTs to `/users/{email}/sendMail`
- `on_send_success` / `on_send_failure`: RQ callbacks that update Prometheus counters
- `SMTPRelayWorker`: custom `Worker` subclass that counts scheduled retries
- `main()`: starts the RQ worker with the delayed-retry scheduler

#### src/oauth.py
Microsoft 365 OAuth2 authentication manager (MSAL `ConfidentialClientApplication`). Handles token acquisition via client credentials flow and file-backed token caching in `token_cache/`.

#### src/config.py
Centralized configuration management, reading all settings from environment variables:
- SMTP server and TLS/SSL settings
- Microsoft Graph API credentials
- Redis / RQ job queue settings
- Rate limiting (incoming)
- Prometheus metrics port
- Security settings (IP whitelist, sender whitelist)

#### src/metrics.py
Prometheus counter/histogram definitions and the `start_metrics_server()` function, including multiprocess-mode aggregation across the relay and worker processes.

#### src/logger.py
Logging configuration using Python's logging module, with rotating file handler + console output.

## Requirements

### System Requirements
- Docker and Docker Compose
- Linux or WSL host
- Minimum 2GB RAM (for all services)
- Redis for the job queue

### Microsoft 365 Requirements
- Entra ID application registration
- Application permissions: `Mail.Send`
- Admin consent granted
- Client credentials (Tenant ID, Client ID, Client Secret)

## Installation

### 1. Clone the Repository
```bash
git clone <repository-url>
cd smtp-relay
```

### 2. Configure Environment Variables

Copy the example environment file and configure:
```bash
cp .env.example .env
```

Edit `.env` with your settings:

```bash
# SMTP Server Configuration
SMTP_RELAY_HOST=0.0.0.0
SMTP_STARTTLS_PORT=587
SMTP_SSL_PORT=465
SMTP_RELAY_USERNAME=your_smtp_username
SMTP_RELAY_PASSWORD=your_smtp_password

# Microsoft Graph API OAuth2
GRAPH_API_TENANT_ID=your_tenant_id
GRAPH_API_CLIENT_ID=your_client_id
GRAPH_API_CLIENT_SECRET=your_client_secret
MS365_EMAIL_ADDRESS=sender@yourdomain.com

# TLS/SSL Configuration
SMTP_RELAY_USE_TLS=true
TLS_CERT_FILE=/app/certs/smtp_relay.crt
TLS_KEY_FILE=/app/certs/smtp_relay.key

# Redis / RQ Job Queue
REDIS_URL=redis://redis:6379/0
RQ_MAX_RETRIES=3
RQ_RETRY_INTERVALS=60,300,900

# Rate Limiting
RATE_LIMIT_PER_MINUTE=60

# Prometheus Metrics
METRICS_PORT=8000

# Prometheus / Alertmanager (monitoring stack)
PROMETHEUS_RETENTION_TIME=90d
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Security
ALLOWED_IPS=*
ALLOWED_SENDERS=*

# Environment
ENVIRONMENT=production
# LOG_LEVEL is not set directly — it follows ENVIRONMENT (DEBUG in
# development, INFO in production)
```

### 3. TLS Certificates (Production)

For production deployment, generate or obtain SSL/TLS certificates:

```bash
# Self-signed certificate (for testing)
openssl req -x509 -newkey rsa:4096 -keyout certs/smtp_relay.key \
  -out certs/smtp_relay.crt -days 365 -nodes \
  -subj "/CN=smtp.yourdomain.com"

# Set proper permissions
chmod 600 certs/smtp_relay.key
chmod 644 certs/smtp_relay.crt
```

For production, use certificates from a trusted CA.

### 4. Entra ID Application Setup

1. Register a new application in Entra ID
2. Configure API permissions:
   - Microsoft Graph > Application permissions > Mail.Send
3. Grant admin consent
4. Create a client secret
5. Note the Tenant ID, Client ID, and Client Secret

### 5. Telegram Bot Setup (Alerts)

1. Create a bot via [@BotFather](https://t.me/BotFather) and note the bot token
2. Add the bot to the chat/group where alerts should go
3. Get the `chat_id` (e.g. via the bot's `getUpdates` API) — negative for groups
4. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`

### 6. Build and Start

```bash
# Build the Docker images
docker compose build

# Start all services
docker compose up -d

# View logs
docker compose logs -f

# View specific service logs
docker compose logs -f smtp-relay
docker compose logs -f worker
```

## Usage

### Sending Emails via the Relay

Configure your application to use the SMTP relay:

**Connection Settings:**
- **Server**: localhost (or your server's IP/domain)
- **Port**: 587 (STARTTLS) or 465 (SSL/TLS)
- **Authentication**: Basic Auth
- **Username**: Value from `SMTP_RELAY_USERNAME`
- **Password**: Value from `SMTP_RELAY_PASSWORD`
- **TLS/SSL**: Enabled in production

Emails are queued immediately and processed asynchronously by the RQ worker.

### Monitoring with Prometheus / Alertmanager

Both bind to `127.0.0.1` only (access via SSH tunnel, not exposed publicly):

```
http://127.0.0.1:9090   # Prometheus — metrics, alert rule states, PromQL queries
http://127.0.0.1:9093   # Alertmanager — active alerts, silences
```

Alerts (permanent send failures, high retry rate, queue backlog, target/Redis down) are delivered to the configured Telegram chat.

### Testing

Test scripts are provided in the `test/` directory:

#### Single Email Test
```bash
# Configure test/test_email.py with your settings
cd test
python3 test_email.py
```

#### Bulk Email Test
```bash
# Configure test/test_mass_email.py with your settings
cd test
python3 test_mass_email.py
```

### Docker Commands

```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# View logs
docker compose logs -f

# Restart specific service
docker compose restart worker

# Rebuild after code changes
docker compose build --no-cache
docker compose up -d

# Access Redis CLI
docker compose exec redis redis-cli

# Check queue/worker status
docker compose exec worker rq info --url redis://redis:6379/0
```

## Configuration Reference

### Core SMTP Settings
- `SMTP_RELAY_HOST`: Server bind address (default: `0.0.0.0`)
- `SMTP_STARTTLS_PORT`: STARTTLS port (default: `587`)
- `SMTP_SSL_PORT`: SSL/TLS port (default: `465`)
- `SMTP_RELAY_USERNAME`: Authentication username
- `SMTP_RELAY_PASSWORD`: Authentication password

### TLS/SSL Settings
- `SMTP_RELAY_USE_TLS`: Enable TLS (forced `true` in production, regardless of this value)
- `TLS_CERT_FILE`: Path to certificate file
- `TLS_KEY_FILE`: Path to private key file

### Microsoft Graph API
- `GRAPH_API_TENANT_ID`: Azure AD tenant ID
- `GRAPH_API_CLIENT_ID`: Application client ID
- `GRAPH_API_CLIENT_SECRET`: Application client secret
- `MS365_EMAIL_ADDRESS`: Sender email address

### Redis / RQ Job Queue
- `REDIS_URL`: Redis connection URL (default: `redis://redis:6379/0`)
- `RQ_MAX_RETRIES`: Maximum retry attempts (default: `3`)
- `RQ_RETRY_INTERVALS`: Comma-separated retry delays in seconds (default: `60,300,900`)

### Rate Limiting
- `RATE_LIMIT_PER_MINUTE`: Incoming emails per minute, per sender (default: `60`)

There is no outbound rate limit toward Graph API — transient errors (429, 5xx, network) are handled by RQ's retry intervals above, not by proactive throttling.

### Security
- `ALLOWED_IPS`: IP whitelist (comma-separated exact IPs, or `*` for all)
- `ALLOWED_SENDERS`: Email whitelist (comma-separated or `*` for all)

### Prometheus / Alertmanager
- `METRICS_PORT`: Prometheus metrics HTTP port on the relay (default: `8000`)
- `PROMETHEUS_RETENTION_TIME`: Prometheus TSDB retention (default: `90d`)
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`: Alertmanager's Telegram receiver

## Monitoring and Troubleshooting

### Health Checks

```bash
# Check service status
docker compose ps
```

### Log Files

Logs are stored in `logs/smtp_relay.log`:
- Rotating file handler (10MB max size)
- 5 backup files retained

View logs:
```bash
# Container logs
docker compose logs -f smtp-relay
docker compose logs -f worker

# Application log file
tail -f logs/smtp_relay.log

# Search for errors
grep ERROR logs/smtp_relay.log

# Correlate a failed job's recipient: find its Job ID from the failure line,
# then grep for every log line that mentions it (includes the original
# "Sending email from X to Y" line)
JOB_ID=$(docker compose logs worker | grep "permanently failed" | tail -1 | grep -oP 'Job \K[0-9a-f-]+')
docker compose logs worker | grep "$JOB_ID"
```

### Common Issues

#### Rate Limiting
If you see "Rate limit exceeded" errors:
- Check `RATE_LIMIT_PER_MINUTE`

#### Job Failures
If jobs are failing permanently:
- Check the Prometheus `smtp_relay_emails_failed_total{reason}` metric and the `SMTPRelayEmailPermanentlyFailed` alert
- Review Graph API credentials
- Verify OAuth2 token validity
- Check network connectivity to Microsoft services

#### Redis Connection Issues
If the relay or worker can't connect to Redis:
```bash
# Check Redis status
docker compose exec redis redis-cli ping

# Restart Redis
docker compose restart redis
```

## Architecture Details

### Job Flow

1. Email received by SMTP server
2. Rate limit check for incoming email
3. Email content base64-encoded and enqueued to Redis via RQ
4. SMTP server returns immediate acknowledgment (250 OK)
5. RQ worker picks up the job
6. OAuth2 token acquired or refreshed from cache
7. Email sent via Graph API with full content
8. Retry scheduled on transient failures (per `RQ_RETRY_INTERVALS`)
9. Job marked as success or permanently failed after `RQ_MAX_RETRIES` retries
10. Prometheus counters updated via `on_send_success`/`on_send_failure`

### Error Recovery Flow

```
Job Execution
     |
     v
Graph API Call
     |
     +---> 202 OK ---------> SUCCESS (email sent)
     |
     +---> 400 Bad Request --> REJECT (permanent error, no retry)
     |
     +---> 403 Forbidden ----> REJECT (permanent error, no retry)
     |
     +---> Other status/network error -> RETRY (per RQ_RETRY_INTERVALS)
     |
     v
Retries exhausted? --> PERMANENT FAILURE (smtp_relay_emails_failed_total)
```

### Rate Limiting Strategy

**Incoming Rate Limiting:**
- Applied at SMTP handler level
- Per-sender sliding window
- Configurable via `RATE_LIMIT_PER_MINUTE`
- Immediate rejection with SMTP 451 code

**Outgoing traffic:** no proactive rate limiting toward Graph API. Errors (including 429) are handled by RQ's retry mechanism.

### Retry Logic

Jobs retry on any Graph API response other than 400/403, and on network errors (connection/timeout).

Jobs do NOT retry on:
- Bad request (400 status code)
- Forbidden (403 status code)
- After `RQ_MAX_RETRIES` attempts exceeded

Retry configuration:
- Fixed delays per attempt, set via `RQ_RETRY_INTERVALS` (default `60,300,900` seconds — not exponential backoff)
- Configurable max retries via `RQ_MAX_RETRIES`

## Performance Tuning

### Scaling Workers

RQ supports multiple worker processes consuming the same queue:

```bash
docker compose up -d --scale worker=2
```

There is no built-in outbound rate limiting (see above), so scaling workers directly increases concurrent Graph API calls — watch for 429 responses if you scale up.

### Redis Optimization

Redis is configured with:
- 256MB memory limit
- LRU eviction policy
- Persistent volume (`redis-data`)

For high-volume deployments, consider:
- Increasing maxmemory
- Using Redis Cluster
- Dedicated Redis server

## License

This project is licensed under the MIT License - see the [LICENSE.txt](LICENSE.txt) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Changelog

### Version 1.0.0
- Initial release
- Dual SMTP server support (ports 587 and 465)
- Microsoft Graph API integration with OAuth2
- Environment-based TLS configuration
- Docker containerization
- IP and sender whitelisting
- Rate limiting
- Health checks
