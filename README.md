# SMTP Relay - Basic Auth to Microsoft 365 OAuth2

A production-ready SMTP relay server that bridges legacy applications using Basic Authentication with Microsoft 365's modern OAuth2 authentication via Microsoft Graph API.

## Overview

This SMTP relay server enables legacy applications that only support basic SMTP authentication to send emails through Microsoft 365 accounts, which require OAuth2 authentication. The relay acts as an intermediary, accepting basic auth credentials and forwarding emails using Microsoft Graph API with OAuth2 tokens.

## Architecture

### Core Components

```
smtp-relay/
├── src/                    # Core application source code
│   ├── __init__.py
│   ├── main.py            # Application entry point and server setup
│   ├── relay.py           # SMTP server handlers and controllers
│   ├── oauth.py           # Microsoft OAuth2 authentication handler
│   ├── config.py          # Configuration management
│   └── logger.py          # Logging configuration
├── test/                  # Test scripts
│   ├── test_email.py      # Single email test with attachment
│   └── test_mass_email.py # Bulk email testing
├── scripts/               # Docker and startup scripts
│   ├── entrypoint.sh      # Docker container entrypoint
│   └── start.sh           # Application startup script
├── certs/                 # TLS/SSL certificates (production)
├── logs/                  # Application logs
├── token_cache/           # OAuth2 token cache
├── docker-compose.yml     # Docker compose configuration
├── Dockerfile            # Docker image definition
├── requirements.txt      # Python dependencies
```

### Module Descriptions

#### src/main.py
Main application entry point. Initializes and starts dual SMTP servers:
- Port 587: STARTTLS server (optional encryption in development, mandatory in production)
- Port 465: SSL/TLS server (implicit encryption when TLS is enabled)

Validates configuration, creates TLS contexts, and manages server lifecycle.

#### src/relay.py
SMTP protocol handlers and server controllers. Contains:
- `SMTPRelayHandler`: Handles SMTP commands (RCPT, DATA) and relays messages via Graph API
- `RateLimiter`: Implements rate limiting per sender
- `AuthenticatedSMTPController`: STARTTLS server controller with authentication
- `SSLSMTPController`: SSL/TLS server controller for implicit encryption
- `AuthenticatedSMTP`: Custom SMTP server with authentication support

#### src/oauth.py
Microsoft 365 OAuth2 authentication manager. Handles:
- Token acquisition using client credentials flow
- Token caching and automatic refresh
- Microsoft Graph API endpoint configuration (configurable for sovereign clouds)
- Application-level permissions (Mail.Send)

#### src/config.py
Centralized configuration management. Loads settings from environment variables:
- SMTP server configuration (host, ports)
- TLS/SSL settings (auto-configured based on environment)
- Microsoft Graph API credentials and endpoints
- Security settings (IP whitelist, sender whitelist)
- Rate limiting and logging configuration

Enforces security policies:
- TLS is mandatory in production
- Certificate validation
- Environment-specific defaults

#### src/logger.py
Logging configuration using Python's logging module. Features:
- Rotating file handler (10MB max, 5 backup files)
- Console output with color-coded levels
- Structured log format with timestamps
- Environment-based log levels (DEBUG in development, INFO in production)

## Features

### Dual SMTP Server Support
- **Port 587 (STARTTLS)**: Modern email clients with optional/required encryption
- **Port 465 (SSL/TLS)**: Legacy clients with implicit SSL encryption

### Security
- **Environment-based TLS enforcement**: Mandatory in production, optional in development
- **IP Whitelist**: Restrict connections by source IP address
- **Sender Whitelist**: Control which email addresses can send through the relay
- **Rate Limiting**: Prevent abuse with configurable rate limits
- **OAuth2 Token Management**: Secure token storage and automatic refresh

### Microsoft Graph API Integration
- Application-level permissions
- Automatic token refresh
- Full email support (HTML, attachments, multiple recipients)
- Sent items saved to Microsoft 365 mailbox

### Operational Features
- Docker containerization
- Health checks
- Structured logging
- Automatic permission management for mounted volumes
- Environment variable validation on startup

## Requirements

### System Requirements
- Docker and Docker Compose
- Linux or WSL host

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

Copy the example environment file:
```bash
cp .env.example .env
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

For production, use certificates from a trusted CA (Let's Encrypt, DigiCert, etc.).

### 4. Entra ID Application Setup

1. Register a new application in Entra ID
2. Configure API permissions:
   - Microsoft Graph > Application permissions > Mail.Send
3. Grant admin consent
4. Create a client secret
5. Note the Tenant ID, Client ID, and Client Secret

### 5. Build and Start

```bash
# Build the Docker image
docker compose build

# Start the service
docker compose up -d

# View logs
docker compose logs -f
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
- **TLS/SSL**: Enabled in production, optional in development

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
# Start the service
docker compose up -d

# Stop the service
docker compose down

# View logs
docker compose logs -f smtp-relay

# Restart the service
docker compose restart

# Rebuild after code changes
docker compose build --no-cache && docker compose up -d
```

## Configuration Reference

#### Microsoft Graph API Endpoints
- `GRAPH_API_AUTHORITY_BASE`: OAuth2 authority base URL (default: `https://login.microsoftonline.com`)
- `GRAPH_API_ENDPOINT`: Graph API endpoint base URL (default: `https://graph.microsoft.com/v1.0`)
- `GRAPH_API_SCOPE`: OAuth2 scope for Graph API (default: `https://graph.microsoft.com/.default`)


#### Security
- `ALLOWED_IPS`: IP whitelist (`*` for all, or comma-separated IPs)
- `ALLOWED_SENDERS`: Email whitelist (`*` for all, or comma-separated emails)

#### Logging & Performance
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `RATE_LIMIT_PER_MINUTE`: Maximum emails per minute per sender (default: 60)


## Monitoring

### Health Checks

Docker health check verifies both SMTP ports are accessible:
```bash
docker compose ps
# Look for "healthy" status
```

### Log Files

Logs are stored in `logs/smtp_relay.log`:
- Rotating file handler (10MB max size)
- 5 backup files retained
- Structured format with timestamps

View logs:
```bash
# Container logs
docker compose logs -f smtp-relay

# Application log file
tail -f logs/smtp_relay.log

# Search for errors
grep ERROR logs/smtp_relay.log
```

### Container Resources

Modify docker-compose.yml to set resource limits:
```yaml
services:
  smtp-relay:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          cpus: '0.5'
          memory: 256M
```

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
