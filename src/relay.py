"""
SMTP Relay Server Handler
Accepts connections from basic auth and relays to Microsoft 365 via Graph API
Uses Celery for asynchronous email processing with rate limiting
"""
import base64
import requests
import json
import ssl
import asyncio
from email.parser import BytesParser
from email.policy import default
from email.utils import parseaddr
from aiosmtpd.smtp import SMTP as SMTPServer, Envelope, AuthResult, LoginPassword
from aiosmtpd.controller import Controller
from datetime import datetime, timedelta
from collections import defaultdict
from .config import Config
from .logger import logger
from .oauth import MS365OAuth

class RateLimiter:
    """Rate limiter for incoming email requests"""
    
    def __init__(self, max_per_minute):
        self.max_per_minute = max_per_minute
        self.requests = defaultdict(list)
    
    def is_allowed(self, identifier):
        """Check if request is allowed under rate limit"""
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        
        # Clean old entries
        self.requests[identifier] = [
            req_time for req_time in self.requests[identifier]
            if req_time > minute_ago
        ]
        
        # Check limit
        if len(self.requests[identifier]) >= self.max_per_minute:
            return False
        
        # Add current request
        self.requests[identifier].append(now)
        return True


class SMTPRelayHandler:
    """SMTP Relay handler that bridges basic auth to OAuth2 via Celery task queue"""
    
    def __init__(self, task_sender):
        """
        Initialize SMTP relay handler
        
        Args:
            task_sender: Callable that sends tasks to queue
        """
        self.oauth = MS365OAuth()
        self.rate_limiter = RateLimiter(Config.INCOMING_RATE_LIMIT_PER_MINUTE)
        self.authenticated_sessions = set()
        self.task_sender = task_sender
        
    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        """Handle RCPT TO command"""
        
        # Get client IP
        peer = session.peer
        client_ip = peer[0] if peer else 'unknown'
        
        # Check if connecting IP is allowed
        if not Config.is_ip_allowed(client_ip):
            logger.warning(f"Rejected connection from unauthorized IP: {client_ip}")
            return '550 5.7.1 Connection from this IP address not allowed'
        
        # Check if sender is allowed
        if not Config.is_sender_allowed(envelope.mail_from):
            logger.warning(f"Rejected email from unauthorized sender: {envelope.mail_from} (IP: {client_ip})")
            return '550 5.7.1 Sender not allowed'
        
        envelope.rcpt_tos.append(address)
        logger.debug(f"Accepted recipient: {address} from {client_ip}")
        return '250 OK'
    
    async def handle_DATA(self, server, session, envelope):
        """Handle DATA command - queue email for processing via Celery"""
        
        try:
            # Get client information
            peer = session.peer
            client_ip = peer[0] if peer else 'unknown'
            
            # Rate limiting check for incoming emails
            if not self.rate_limiter.is_allowed(envelope.mail_from):
                logger.warning(
                    f"Incoming rate limit exceeded for {envelope.mail_from} "
                    f"from {client_ip}"
                )
                return '451 4.7.1 Rate limit exceeded. Please try again later.'
            
            # Log email details
            logger.info(
                f"Queuing email from {envelope.mail_from} to {envelope.rcpt_tos} "
                f"(client: {client_ip})"
            )
            
            # Encode email content for serialization
            content_b64 = base64.b64encode(envelope.content).decode('utf-8')
            
            # Prepare envelope data for task
            envelope_data = {
                'mail_from': envelope.mail_from,
                'rcpt_tos': envelope.rcpt_tos,
                'content': content_b64,
                'client_ip': client_ip,
            }
            
            # Queue task asynchronously
            task = self.task_sender(envelope_data)
            
            logger.info(
                f"Email queued successfully with task ID: {task.id} "
                f"from {envelope.mail_from}"
            )
            
            return '250 Message accepted for delivery'
            
        except Exception as e:
            logger.error(f"Error queuing email: {e}", exc_info=True)
            return f'451 Error processing message: {str(e)}'


class AuthenticatedSMTPController(Controller):
    """SMTP Controller with authentication support for STARTTLS"""
    
    def __init__(self, handler, tls_context=None, require_starttls=False, **kwargs):
        self.handler_instance = handler
        self.tls_context = tls_context
        self.require_starttls = require_starttls
        self.auth_require_tls = require_starttls  # If STARTTLS is required, auth also requires TLS
        super().__init__(handler, **kwargs)
    
    def factory(self):
        """Create SMTP server instance with authentication"""
        return AuthenticatedSMTP(
            self.handler_instance,
            require_starttls=self.require_starttls,
            tls_context=self.tls_context,
            authenticator=self._authenticate,
            auth_require_tls=self.auth_require_tls,
            enable_SMTPUTF8=True,
        )
    
    def _authenticate(self, server, session, envelope, mechanism, auth_data):
        """Authentication callback for SMTP server"""
        fail_nothandled = AuthResult(success=False, handled=False)
        
        if mechanism not in ("LOGIN", "PLAIN"):
            return fail_nothandled
        
        # Decode authentication data (be defensive: aiosmtpd may provide bytes or LoginPassword)
        username = None
        password = None
        try:
            # If auth_data is a LoginPassword-like object
            if hasattr(auth_data, 'login') and hasattr(auth_data, 'password'):
                login_val = auth_data.login
                pwd_val = auth_data.password
                username = login_val.decode('utf-8') if isinstance(login_val, (bytes, bytearray)) else str(login_val)
                password = pwd_val.decode('utf-8') if isinstance(pwd_val, (bytes, bytearray)) else str(pwd_val)

            # If auth_data is raw bytes (common for PLAIN)
            elif isinstance(auth_data, (bytes, bytearray)):
                parts = auth_data.split(b'\0')
                if len(parts) == 3:
                    username = parts[1].decode('utf-8', errors='ignore')
                    password = parts[2].decode('utf-8', errors='ignore')
                else:
                    # Sometimes the auth_data may be a base64-decoded string without leading NUL
                    try:
                        s = auth_data.decode('utf-8', errors='ignore')
                        parts = s.split('\0')
                        if len(parts) == 3:
                            username = parts[1]
                            password = parts[2]
                    except Exception:
                        pass

            # If auth_data is a plain string
            elif isinstance(auth_data, str):
                parts = auth_data.split('\0')
                if len(parts) == 3:
                    username = parts[1]
                    password = parts[2]

        except Exception as e:
            logger.exception(f"Error parsing auth_data: {e}")
            return AuthResult(success=False, handled=True)
        
        # If parsing failed, don't claim not-handled; return handled=False so other auth handlers could try
        if username is None or password is None:
            logger.warning("Authentication data in unexpected format")
            return fail_nothandled

        # Validate credentials
        if username == Config.SMTP_RELAY_USERNAME and password == Config.SMTP_RELAY_PASSWORD:
            logger.info(f"Successful authentication for user: {username}")
            return AuthResult(success=True, handled=True)
        else:
            logger.warning(f"Failed authentication attempt for user: {username}")
            return AuthResult(success=False, handled=True)


class SSLSMTPController(Controller):
    """SMTP Controller with implicit SSL support (port 465)"""
    
    def __init__(self, handler, tls_context=None, **kwargs):
        self.handler_instance = handler
        self.tls_context = tls_context
        # Pass ssl_context to parent Controller - it handles SSL implicitly
        super().__init__(handler, ssl_context=tls_context, **kwargs)
    
    def factory(self):
        """Create SMTP server instance with authentication (no STARTTLS for SSL mode)"""
        return AuthenticatedSMTP(
            self.handler_instance,
            require_starttls=False,
            tls_context=None,  # SSL is at server level, not SMTP level
            authenticator=self._authenticate,
            auth_require_tls=False,
            enable_SMTPUTF8=True,
        )
    
    def _authenticate(self, server, session, envelope, mechanism, auth_data):
        """Authentication callback for SMTP server"""
        fail_nothandled = AuthResult(success=False, handled=False)
        
        if mechanism not in ("LOGIN", "PLAIN"):
            return fail_nothandled
        
        # Decode authentication data
        username = None
        password = None
        try:
            if hasattr(auth_data, 'login') and hasattr(auth_data, 'password'):
                login_val = auth_data.login
                pwd_val = auth_data.password
                username = login_val.decode('utf-8') if isinstance(login_val, (bytes, bytearray)) else str(login_val)
                password = pwd_val.decode('utf-8') if isinstance(pwd_val, (bytes, bytearray)) else str(pwd_val)
            elif isinstance(auth_data, (bytes, bytearray)):
                parts = auth_data.split(b'\0')
                if len(parts) == 3:
                    username = parts[1].decode('utf-8', errors='ignore')
                    password = parts[2].decode('utf-8', errors='ignore')
            elif isinstance(auth_data, str):
                parts = auth_data.split('\0')
                if len(parts) == 3:
                    username = parts[1]
                    password = parts[2]
        except Exception as e:
            logger.exception(f"Error parsing auth_data: {e}")
            return AuthResult(success=False, handled=True)
        
        if username is None or password is None:
            logger.warning("Authentication data in unexpected format")
            return fail_nothandled

        # Validate credentials
        if username == Config.SMTP_RELAY_USERNAME and password == Config.SMTP_RELAY_PASSWORD:
            logger.info(f"Successful authentication for user: {username}")
            return AuthResult(success=True, handled=True)
        else:
            logger.warning(f"Failed authentication attempt for user: {username}")
            return AuthResult(success=False, handled=True)
    
    def _authenticate(self, server, session, envelope, mechanism, auth_data):
        """Authentication callback for SMTP server"""
        fail_nothandled = AuthResult(success=False, handled=False)
        
        if mechanism not in ("LOGIN", "PLAIN"):
            return fail_nothandled
        
        # Decode authentication data (be defensive: aiosmtpd may provide bytes or LoginPassword)
        username = None
        password = None
        try:
            # If auth_data is a LoginPassword-like object
            if hasattr(auth_data, 'login') and hasattr(auth_data, 'password'):
                login_val = auth_data.login
                pwd_val = auth_data.password
                username = login_val.decode('utf-8') if isinstance(login_val, (bytes, bytearray)) else str(login_val)
                password = pwd_val.decode('utf-8') if isinstance(pwd_val, (bytes, bytearray)) else str(pwd_val)

            # If auth_data is raw bytes (common for PLAIN)
            elif isinstance(auth_data, (bytes, bytearray)):
                parts = auth_data.split(b'\0')
                if len(parts) == 3:
                    username = parts[1].decode('utf-8', errors='ignore')
                    password = parts[2].decode('utf-8', errors='ignore')
                else:
                    # Sometimes the auth_data may be a base64-decoded string without leading NUL
                    try:
                        s = auth_data.decode('utf-8', errors='ignore')
                        parts = s.split('\0')
                        if len(parts) == 3:
                            username = parts[1]
                            password = parts[2]
                    except Exception:
                        pass

            # If auth_data is a plain string
            elif isinstance(auth_data, str):
                parts = auth_data.split('\0')
                if len(parts) == 3:
                    username = parts[1]
                    password = parts[2]

        except Exception as e:
            logger.exception(f"Error parsing auth_data: {e}")
            return AuthResult(success=False, handled=True)
        
        # If parsing failed, don't claim not-handled; return handled=False so other auth handlers could try
        if username is None or password is None:
            logger.warning("Authentication data in unexpected format")
            return fail_nothandled

        # Validate credentials
        if username == Config.SMTP_RELAY_USERNAME and password == Config.SMTP_RELAY_PASSWORD:
            logger.info(f"Successful authentication for user: {username}")
            return AuthResult(success=True, handled=True)
        else:
            logger.warning(f"Failed authentication attempt for user: {username}")
            return AuthResult(success=False, handled=True)


class AuthenticatedSMTP(SMTPServer):
    """Custom SMTP server with authentication"""
    
    def __init__(self, handler, **kwargs):
        self.handler_instance = handler
        super().__init__(handler, **kwargs)
