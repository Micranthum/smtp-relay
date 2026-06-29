"""
Configuration management for SMTP Relay
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Configuration class for SMTP Relay"""
    
    # Environment Configuration
    ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
    
    # SMTP Relay Server Configuration
    SMTP_RELAY_HOST = os.getenv('SMTP_RELAY_HOST', '0.0.0.0')
    
    # Dual server setup
    SMTP_STARTTLS_PORT = os.getenv('SMTP_STARTTLS_PORT', 587)
    SMTP_SSL_PORT = os.getenv('SMTP_SSL_PORT', 465)
    
    # TLS/SSL - FORCED in production, optional in development
    # Production ALWAYS requires TLS for security, cannot be disabled
    if ENVIRONMENT == 'production':
        SMTP_RELAY_USE_TLS = True  # FORCED - cannot be disabled in production
    else:
        SMTP_RELAY_USE_TLS = os.getenv('SMTP_RELAY_USE_TLS', 'false').lower() == 'true'

    # TLS/SSL Certificate Configuration (required when TLS is enabled)
    TLS_CERT_FILE = os.getenv('TLS_CERT_FILE', '')  # Path to certificate file
    TLS_KEY_FILE = os.getenv('TLS_KEY_FILE', '')    # Path to private key file
    
    # Basic Auth Credentials
    SMTP_RELAY_USERNAME = os.getenv('SMTP_RELAY_USERNAME', '')
    SMTP_RELAY_PASSWORD = os.getenv('SMTP_RELAY_PASSWORD', '')
    
    # Microsoft Graph API OAuth2 Configuration
    GRAPH_API_TENANT_ID = os.getenv('GRAPH_API_TENANT_ID', '')
    GRAPH_API_CLIENT_ID = os.getenv('GRAPH_API_CLIENT_ID', '')
    GRAPH_API_CLIENT_SECRET = os.getenv('GRAPH_API_CLIENT_SECRET', '')
    MS365_EMAIL_ADDRESS = os.getenv('MS365_EMAIL_ADDRESS', '')
    
    # Microsoft Graph API Endpoints
    GRAPH_API_AUTHORITY_BASE = os.getenv('GRAPH_API_AUTHORITY_BASE', 'https://login.microsoftonline.com')
    GRAPH_API_ENDPOINT = os.getenv('GRAPH_API_ENDPOINT', 'https://graph.microsoft.com/v1.0')
    GRAPH_API_SCOPE = os.getenv('GRAPH_API_SCOPE', 'https://graph.microsoft.com/.default')
    
    # Security - IP Whitelist
    ALLOWED_IPS = os.getenv('ALLOWED_IPS', '*')
    # Examples: 
    # - '*' = Allow all IPs (development)
    # - '192.168.1.100,10.0.0.50' = Allow specific IPs (production)
    
    # Security - Email Whitelist
    ALLOWED_SENDERS = os.getenv('ALLOWED_SENDERS', '*')
    # Examples:
    # - '*' = Allow all senders (development)
    # - 'user1@domain.com,user2@domain.com' = Allow specific senders (production)
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'DEBUG' if ENVIRONMENT == 'development' else 'INFO')
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE = int(os.getenv('RATE_LIMIT_PER_MINUTE', '60'))

    # Redis / RQ Job Queue
    REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')
    RQ_MAX_RETRIES = int(os.getenv('RQ_MAX_RETRIES', '3'))
    RQ_RETRY_INTERVALS = [
        int(x) for x in os.getenv('RQ_RETRY_INTERVALS', '60,300,900').split(',')
    ]

    # Prometheus Metrics HTTP Server
    METRICS_PORT = int(os.getenv('METRICS_PORT', '8000'))
    # PROMETHEUS_MULTIPROC_DIR is read directly from os.environ by prometheus_client
    # at import time — set it as an env var before Python starts, not here.
    
    @classmethod
    def validate(cls):
        """Validate required configuration"""
        errors = []
        
        # Security warning if someone tries to disable TLS in production
        if cls.ENVIRONMENT == 'production':
            env_tls = os.getenv('SMTP_RELAY_USE_TLS', '').lower()
            if env_tls == 'false':
                print("=" * 70)
                print("SECURITY WARNING: Attempted to disable TLS in production!")
                print("TLS is MANDATORY in production and has been force-enabled.")
                print("Remove SMTP_RELAY_USE_TLS=false from your .env file.")
                print("=" * 70)
        
        # Required fields
        if not cls.SMTP_RELAY_USERNAME:
            errors.append("SMTP_RELAY_USERNAME is required")
        if not cls.SMTP_RELAY_PASSWORD:
            errors.append("SMTP_RELAY_PASSWORD is required")
        if not cls.GRAPH_API_TENANT_ID:
            errors.append("GRAPH_API_TENANT_ID is required")
        if not cls.GRAPH_API_CLIENT_ID:
            errors.append("GRAPH_API_CLIENT_ID is required")
        if not cls.GRAPH_API_CLIENT_SECRET:
            errors.append("GRAPH_API_CLIENT_SECRET is required")
        if not cls.MS365_EMAIL_ADDRESS:
            errors.append("MS365_EMAIL_ADDRESS is required")
        
        # TLS Certificate validation (only required when TLS is enabled)
        if cls.SMTP_RELAY_USE_TLS:
            if not cls.TLS_CERT_FILE or not cls.TLS_KEY_FILE:
                errors.append("TLS_CERT_FILE and TLS_KEY_FILE are required when SMTP_RELAY_USE_TLS is enabled")
            else:
                cert_path = Path(cls.TLS_CERT_FILE)
                key_path = Path(cls.TLS_KEY_FILE)
                if not cert_path.exists():
                    errors.append(f"TLS certificate file not found: {cls.TLS_CERT_FILE}")
                if not key_path.exists():
                    errors.append(f"TLS key file not found: {cls.TLS_KEY_FILE}")
        
        # Production-specific validations
        if cls.ENVIRONMENT == 'production':
            if cls.LOG_LEVEL == 'DEBUG':
                errors.append("LOG_LEVEL should not be 'DEBUG' in production")
            # TLS is now always enabled in production, so this check is redundant but kept for clarity
            if not cls.SMTP_RELAY_USE_TLS:
                errors.append("CRITICAL: TLS must be enabled in production mode (this should never happen)")
        else:
            # Development mode warning
            if not cls.SMTP_RELAY_USE_TLS:
                print(f"WARNING: Running in development mode without TLS enabled. Connections will not be encrypted.")
        
        if errors:
            raise ValueError(f"Configuration errors:\n  - " + "\n  - ".join(errors))
        
        return True
    
    @classmethod
    def is_sender_allowed(cls, email: str) -> bool:
        """Check if sender email is allowed"""
        if cls.ALLOWED_SENDERS == '*':
            return True
        allowed = [s.strip().lower() for s in cls.ALLOWED_SENDERS.split(',')]
        return email.lower() in allowed
    
    @classmethod
    def is_ip_allowed(cls, ip: str) -> bool:
        """Check if connecting IP is allowed"""
        if cls.ALLOWED_IPS == '*':
            return True
        allowed = [s.strip() for s in cls.ALLOWED_IPS.split(',')]
        return ip in allowed
    
    @classmethod
    def is_production(cls) -> bool:
        """Check if running in production mode"""
        return cls.ENVIRONMENT == 'production'
    
    @classmethod
    def is_development(cls) -> bool:
        """Check if running in development mode"""
        return cls.ENVIRONMENT == 'development'
