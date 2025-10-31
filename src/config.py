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
    ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')  # development or production
    
    # SMTP Relay Server Configuration
    SMTP_RELAY_HOST = os.getenv('SMTP_RELAY_HOST', '0.0.0.0')
    SMTP_RELAY_PORT = int(os.getenv('SMTP_RELAY_PORT', '587'))
    SMTP_RELAY_USE_TLS = os.getenv('SMTP_RELAY_USE_TLS', 'false').lower() == 'true'
    
    # TLS/SSL Certificate Configuration (optional, for production)
    TLS_CERT_FILE = os.getenv('TLS_CERT_FILE', '')  # Path to certificate file
    TLS_KEY_FILE = os.getenv('TLS_KEY_FILE', '')    # Path to private key file
    
    # Basic Auth Credentials
    SMTP_RELAY_USERNAME = os.getenv('SMTP_RELAY_USERNAME', '')
    SMTP_RELAY_PASSWORD = os.getenv('SMTP_RELAY_PASSWORD', '')
    
    # Microsoft 365 SMTP Configuration (legacy, not used with Graph API)
    MS365_SMTP_HOST = os.getenv('MS365_SMTP_HOST', 'smtp.office365.com')
    MS365_SMTP_PORT = int(os.getenv('MS365_SMTP_PORT', '587'))
    
    # Microsoft 365 OAuth2 Configuration
    MS365_TENANT_ID = os.getenv('MS365_TENANT_ID', '')
    MS365_CLIENT_ID = os.getenv('MS365_CLIENT_ID', '')
    MS365_CLIENT_SECRET = os.getenv('MS365_CLIENT_SECRET', '')
    MS365_EMAIL_ADDRESS = os.getenv('MS365_EMAIL_ADDRESS', '')
    
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
    
    @classmethod
    def validate(cls):
        """Validate required configuration"""
        errors = []
        
        # Required fields
        if not cls.SMTP_RELAY_USERNAME:
            errors.append("SMTP_RELAY_USERNAME is required")
        if not cls.SMTP_RELAY_PASSWORD:
            errors.append("SMTP_RELAY_PASSWORD is required")
        if not cls.MS365_TENANT_ID:
            errors.append("MS365_TENANT_ID is required")
        if not cls.MS365_CLIENT_ID:
            errors.append("MS365_CLIENT_ID is required")
        if not cls.MS365_CLIENT_SECRET:
            errors.append("MS365_CLIENT_SECRET is required")
        if not cls.MS365_EMAIL_ADDRESS:
            errors.append("MS365_EMAIL_ADDRESS is required")
        
        # Production-specific validations
        if cls.ENVIRONMENT == 'production':
            if cls.ALLOWED_IPS == '*':
                errors.append("ALLOWED_IPS should not be '*' in production (security risk)")
            # Note: ALLOWED_SENDERS can be '*' if you control access via IP whitelist
            if cls.LOG_LEVEL == 'DEBUG':
                errors.append("LOG_LEVEL should not be 'DEBUG' in production")
        
        # TLS Certificate validation (if enabled)
        if cls.SMTP_RELAY_USE_TLS:
            if not cls.TLS_CERT_FILE or not cls.TLS_KEY_FILE:
                errors.append("TLS_CERT_FILE and TLS_KEY_FILE are required when SMTP_RELAY_USE_TLS is true")
            elif cls.TLS_CERT_FILE and cls.TLS_KEY_FILE:
                cert_path = Path(cls.TLS_CERT_FILE)
                key_path = Path(cls.TLS_KEY_FILE)
                if not cert_path.exists():
                    errors.append(f"TLS certificate file not found: {cls.TLS_CERT_FILE}")
                if not key_path.exists():
                    errors.append(f"TLS key file not found: {cls.TLS_KEY_FILE}")
            
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
