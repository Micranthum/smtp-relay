# SMTP Relay - Basic Auth to Microsoft 365 OAuth2 with Celery Queue

A production-ready SMTP relay server that bridges legacy applications using Basic Authentication with Microsoft 365's modern OAuth2 authentication via Microsoft Graph API. Features asynchronous email processing with Celery task queue, rate limiting, and automatic retries.

## Overview

This SMTP relay server enables legacy applications that only support basic SMTP authentication to send emails through Microsoft 365 accounts, which require OAuth2 authentication. The relay acts as an intermediary, accepting basic auth credentials and queueing emails for asynchronous processing via Celery workers that communicate with Microsoft Graph API using OAuth2 tokens.

## Key Features

### Asynchronous Email Processing
- Celery-based task queue for reliable email delivery
- Redis as message broker and result backend
- Automatic retry mechanism with exponential backoff
- Task persistence and recovery

### Rate Limiting
- Incoming email rate limiting (configurable per sender)
- Outbound Graph API rate limiting (default: 30 emails/minute for Exchange Online)
- Synchronous processing to respect Graph API concurrent request limits (max 4)
- Prevents throttling by Microsoft services

### Monitoring and Observability
- Flower web UI for real-time task monitoring
- Task state tracking and history
- Worker health monitoring
- Comprehensive logging with rotation

## Architecture

### Core Components

```
smtp-relay/
├── src/                    # Core application source code
│   ├── __init__.py
│   ├── main.py            # Application entry point and SMTP server setup
│   ├── relay.py           # SMTP server handlers with Celery integration
│   ├── tasks.py           # Celery tasks for email processing
│   ├── celery_app.py      # Celery application configuration
│   ├── oauth.py           # Microsoft OAuth2 authentication handler
│   ├── config.py          # Configuration management
│   └── logger.py          # Logging configuration
├── scripts/               # Startup scripts
│   ├── entrypoint.sh      # Docker container entrypoint
│   ├── start.sh           # SMTP server startup script
│   └── start_celery.sh    # Celery worker startup script
├── test/                  # Test scripts
├── certs/                 # TLS/SSL certificates (production)
├── logs/                  # Application logs
├── token_cache/           # OAuth2 token cache
├── docker-compose.yml     # Docker compose with all services
├── Dockerfile            # Docker image definition
└── requirements.txt      # Python dependencies
```

### System Architecture

```
┌─────────────────┐
│  Email Client   │
│ (Legacy/Modern) │
└────────┬────────┘
         │ SMTP (587/465)
         ▼
┌─────────────────────────────┐
│   SMTP Relay Server         │
│   - Rate limiting (incoming)│
│   - Authentication          │
│   - Queue to Celery         │
└────────┬────────────────────┘
         │
         ▼
    ┌────────┐
    │ Redis  │ Message Broker
    └───┬────┘
        │
        ▼
┌──────────────────────────┐
│   Celery Worker          │
│   - Rate limiting (30/m) │
│   - Retry logic          │
│   - OAuth2 token mgmt    │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│ Microsoft Graph API      │
│ (Exchange Online)        │
└──────────────────────────┘

      Monitoring:
    ┌────────────┐
    │   Flower   │
    │ (port 5555)│
    └────────────┘
```

### Module Descriptions

#### src/main.py
Main application entry point. Initializes and starts dual SMTP servers:
- Port 587: STARTTLS server (optional encryption in development, mandatory in production)
- Port 465: SSL/TLS server (implicit encryption when TLS is enabled)

Validates configuration, creates TLS contexts, and manages server lifecycle.

#### src/relay.py
SMTP protocol handlers with Celery integration. Contains:
- `SMTPRelayHandler`: Handles SMTP commands and queues emails to Celery
- `RateLimiter`: Implements rate limiting for incoming emails
- `AuthenticatedSMTPController`: STARTTLS server controller with authentication
- `SSLSMTPController`: SSL/TLS server controller for implicit encryption
- `AuthenticatedSMTP`: Custom SMTP server with authentication support

Uses dependency injection for task sender to enable testing and flexibility.

#### src/tasks.py
Celery task definitions for email processing:
- `send_email_via_graph`: Main task for sending emails via Graph API
- `EmailSendTask`: Base task class with OAuth client dependency injection
- Error handling with specific retry logic for different HTTP status codes
- Automatic token refresh on authentication failures

#### src/celery_app.py
Celery application configuration:
- Queue setup with priority support
- Rate limiting configuration for Graph API
- Worker concurrency settings (single worker for synchronous processing)
- Task routing and serialization settings
- Integration with Redis broker

#### src/oauth.py
Microsoft 365 OAuth2 authentication manager. Handles:
- Token acquisition using client credentials flow
- Token caching and automatic refresh
- Microsoft Graph API endpoint configuration
- Application-level permissions (Mail.Send)

#### src/config.py
Centralized configuration management with new Celery-related settings:
- SMTP server configuration
- TLS/SSL settings
- Microsoft Graph API credentials
- Celery broker and backend URLs
- Rate limiting (incoming and outgoing)
- Task retry configuration
- Security settings (IP whitelist, sender whitelist)

#### src/logger.py
Logging configuration using Python's logging module with structured output.

## Requirements

### System Requirements
- Docker and Docker Compose
- Linux or WSL host
- Minimum 2GB RAM (for all services)
- Redis for message queue

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

# Celery Configuration
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# Rate Limiting
INCOMING_RATE_LIMIT_PER_MINUTE=60
GRAPH_API_RATE_LIMIT_PER_MINUTE=30

# Celery Task Configuration
CELERY_MAX_RETRIES=3
CELERY_RETRY_DELAY=60

# Flower Monitoring
FLOWER_PORT=5555

# Security
ALLOWED_IPS=*
ALLOWED_SENDERS=*

# Environment
ENVIRONMENT=production
LOG_LEVEL=INFO
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

### 5. Build and Start

```bash
# Build the Docker images
docker compose build

# Start all services
docker compose up -d

# View logs
docker compose logs -f

# View specific service logs
docker compose logs -f smtp-relay
docker compose logs -f celery-worker
docker compose logs -f flower
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

Emails are queued immediately and processed asynchronously by Celery workers.

### Monitoring with Flower

Access the Flower web interface to monitor email tasks:

```
http://localhost:5555
```

Features:
- Real-time task monitoring
- Task history and states
- Worker status and statistics
- Task filtering and search
- Task retry and revoke

### Testing

Test scripts are provided in the `test/` directory:

#### Verify Celery Configuration
```bash
# After starting services, verify Celery is properly configured
python3 test/test_celery_config.py
```

This will check:
- Broker connection
- Active workers
- Registered tasks

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
docker compose restart celery-worker

# Rebuild after code changes
docker compose build --no-cache
docker compose up -d

# Scale Celery workers (if needed)
docker compose up -d --scale celery-worker=3

# Access Redis CLI
docker compose exec redis redis-cli

# Check worker status
docker compose exec celery-worker celery -A src.celery_app inspect active
```

## Configuration Reference

### Core SMTP Settings
- `SMTP_RELAY_HOST`: Server bind address (default: `0.0.0.0`)
- `SMTP_STARTTLS_PORT`: STARTTLS port (default: `587`)
- `SMTP_SSL_PORT`: SSL/TLS port (default: `465`)
- `SMTP_RELAY_USERNAME`: Authentication username
- `SMTP_RELAY_PASSWORD`: Authentication password

### TLS/SSL Settings
- `SMTP_RELAY_USE_TLS`: Enable TLS (forced in production)
- `TLS_CERT_FILE`: Path to certificate file
- `TLS_KEY_FILE`: Path to private key file

### Microsoft Graph API
- `GRAPH_API_TENANT_ID`: Azure AD tenant ID
- `GRAPH_API_CLIENT_ID`: Application client ID
- `GRAPH_API_CLIENT_SECRET`: Application client secret
- `MS365_EMAIL_ADDRESS`: Sender email address

### Celery Configuration
- `CELERY_BROKER_URL`: Redis broker URL (default: `redis://redis:6379/0`)
- `CELERY_RESULT_BACKEND`: Result backend URL (default: `redis://redis:6379/0`)
- `CELERY_MAX_RETRIES`: Maximum retry attempts (default: `3`)
- `CELERY_RETRY_DELAY`: Initial retry delay in seconds (default: `60`)

### Rate Limiting
- `INCOMING_RATE_LIMIT_PER_MINUTE`: Incoming emails per minute (default: `60`)
- `GRAPH_API_RATE_LIMIT_PER_MINUTE`: Outgoing emails per minute (default: `30`)

Note: The Graph API rate limit is enforced by Celery task rate limiting. The worker processes tasks sequentially to respect Microsoft's concurrent request limits.

### Security
- `ALLOWED_IPS`: IP whitelist (comma-separated or `*` for all)
- `ALLOWED_SENDERS`: Email whitelist (comma-separated or `*` for all)

### Monitoring
- `FLOWER_PORT`: Flower web interface port (default: `5555`)

## Monitoring and Troubleshooting

### Health Checks

All services include health checks:

```bash
# Check service status
docker compose ps

# All services should show "healthy"
```

### Log Files

Logs are stored in `logs/smtp_relay.log`:
- Rotating file handler (10MB max size)
- 5 backup files retained

View logs:
```bash
# Container logs
docker compose logs -f smtp-relay
docker compose logs -f celery-worker

# Application log file
tail -f logs/smtp_relay.log

# Search for errors
grep ERROR logs/smtp_relay.log

# Filter by task ID
grep "task_id_here" logs/smtp_relay.log
```

### Celery Task Management

```bash
# Inspect active tasks
docker compose exec celery-worker celery -A src.celery_app inspect active

# Inspect scheduled tasks
docker compose exec celery-worker celery -A src.celery_app inspect scheduled

# Inspect registered tasks
docker compose exec celery-worker celery -A src.celery_app inspect registered

# Purge all tasks from queue
docker compose exec celery-worker celery -A src.celery_app purge

# Get worker statistics
docker compose exec celery-worker celery -A src.celery_app inspect stats
```

### Common Issues

#### Rate Limiting
If you see "Rate limit exceeded" errors:
- Check `INCOMING_RATE_LIMIT_PER_MINUTE` for incoming emails
- Check `GRAPH_API_RATE_LIMIT_PER_MINUTE` for outgoing emails
- Monitor Flower for task queue buildup

#### Task Failures
If tasks are failing:
- Check Flower for error messages
- Review Graph API credentials
- Verify OAuth2 token validity
- Check network connectivity to Microsoft services

#### Redis Connection Issues
If workers can't connect to Redis:
```bash
# Check Redis status
docker compose exec redis redis-cli ping

# Restart Redis
docker compose restart redis
```

## Architecture Details

### Task Flow

1. Email received by SMTP server
2. Rate limit check for incoming email
3. Email serialized and queued to Celery via Redis
4. SMTP server returns immediate acknowledgment (250 OK)
5. Celery worker picks up task from queue
6. Rate limiting applied for Graph API (30/min default)
7. OAuth2 token acquired or refreshed from cache
8. Email sent via Graph API with full content
9. Retry logic activated on transient failures
10. Task marked as success or failure
11. Results stored in Redis backend

### Error Recovery Flow

```
Task Execution
     |
     v
Graph API Call
     |
     +---> 202 OK ---------> SUCCESS (email sent)
     |
     +---> 429 Rate Limit --> RETRY (after Retry-After seconds)
     |
     +---> 503 Unavailable -> RETRY (exponential backoff)
     |
     +---> 401 Unauthorized -> Clear token + RETRY
     |
     +---> 400 Bad Request --> REJECT (permanent error)
     |
     +---> 403 Forbidden ----> REJECT (permission error)
     |
     +---> Network Error ----> RETRY (exponential backoff)
     |
     v
Max Retries? --> FAILURE (after configured attempts)
```

### Rate Limiting Strategy

**Incoming Rate Limiting:**
- Applied at SMTP handler level
- Per-sender basis
- Configurable via `INCOMING_RATE_LIMIT_PER_MINUTE`
- Immediate rejection with 451 code

**Outgoing Rate Limiting:**
- Applied at Celery task level
- Global limit for Graph API
- Configurable via `GRAPH_API_RATE_LIMIT_PER_MINUTE`
- Default: 30 emails/minute (Exchange Online limit)
- Tasks delayed if rate exceeded

**Synchronous Processing:**
- Worker concurrency set to 1
- Prevents exceeding Graph API concurrent request limit (4)
- Ensures predictable rate limiting
- Tasks processed sequentially

### Retry Logic

Tasks automatically retry on:
- Network errors (connection timeout, DNS failures)
- Rate limiting (429 status code)
- Service unavailable (503 status code)
- Authentication failures (401 status code)

Tasks do NOT retry on:
- Bad request (400 status code)
- Forbidden (403 status code)
- After maximum retry attempts exceeded

Retry configuration:
- Exponential backoff
- Jitter to prevent thundering herd
- Configurable max retries and delay

## Performance Tuning

### Scaling Workers

For higher throughput (if Graph API limits allow):

```yaml
# In docker-compose.yml, increase concurrency carefully
# Note: Must respect Graph API concurrent request limit (4)
celery-worker:
  command: celery -A src.celery_app worker --concurrency=2
```

Or scale worker instances:
```bash
docker compose up -d --scale celery-worker=2
```

Warning: Increasing concurrency may cause Graph API throttling.

### Redis Optimization

Redis is configured with:
- 256MB memory limit
- LRU eviction policy
- Persistent storage

For high-volume deployments, consider:
- Increasing maxmemory
- Using Redis Cluster
- Dedicated Redis server

### Resource Limits

Set resource limits in docker-compose.yml:

```yaml
services:
  celery-worker:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
```

## License

This project is licensed under the MIT License - see the [LICENSE.txt](LICENSE.txt) file for details.

## Technical Details

### Celery Task Queue

The system uses Celery with Redis as the message broker for asynchronous email processing. This architecture provides:

**Benefits:**
- Immediate SMTP acknowledgment (emails queued instantly)
- Automatic retry mechanism with exponential backoff
- Rate limiting compliance for Microsoft Graph API
- Task persistence and recovery after failures
- Horizontal scalability through worker instances

**Task States:**
- PENDING: Task waiting in queue
- STARTED: Task picked up by worker
- RETRY: Task being retried after failure
- SUCCESS: Email sent successfully
- FAILURE: Permanent failure after max retries

**Error Handling:**
- 429 (Rate Limit): Retry after delay specified in Retry-After header
- 503 (Service Unavailable): Retry with exponential backoff
- 401 (Unauthorized): Clear token cache and retry
- 400/403: Permanent errors, no retry
- Network errors: Automatic retry with backoff

### Dependency Injection

The codebase follows dependency injection principles for testability and flexibility:

**SMTPRelayHandler:**
```python
# Constructor accepts optional task_sender for testing
handler = SMTPRelayHandler(task_sender=mock_sender)
```

**EmailSendTask:**
```python
# OAuth client injected as property for worker reuse
class EmailSendTask(Task):
    @property
    def oauth_client(self):
        # Lazy initialization, shared across tasks
```

This design allows:
- Unit testing without actual Celery infrastructure
- Easy mocking of external dependencies
- Reusable components across different contexts

### Rate Limiting Implementation

**Incoming (SMTP Level):**
- Time-window based algorithm
- Per-sender tracking
- Sliding window of 1 minute
- Immediate rejection with SMTP 451 code

**Outgoing (Celery Level):**
- Celery task rate limiting
- Global limit across all workers
- Token bucket algorithm
- Tasks delayed, not rejected

**Synchronous Processing:**
- Worker concurrency set to 1
- Prevents exceeding Graph API concurrent limits
- Ensures predictable throughput
- Simplifies rate limit calculations


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
