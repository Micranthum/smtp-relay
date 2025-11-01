"""
SMTP Relay Server Handler
Accepts connections from Contpaq with basic auth and relays to Microsoft 365 via Graph API
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
    """Simple rate limiter for email sending"""
    
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
    """SMTP Relay handler that bridges basic auth to OAuth2"""
    
    def __init__(self):
        self.oauth = MS365OAuth()
        self.rate_limiter = RateLimiter(Config.RATE_LIMIT_PER_MINUTE)
        self.authenticated_sessions = set()
        
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
        """Handle DATA command - relay email to Microsoft 365"""
        
        try:
            # Get client information
            peer = session.peer
            client_ip = peer[0] if peer else 'unknown'
            
            # Rate limiting check
            if not self.rate_limiter.is_allowed(envelope.mail_from):
                logger.warning(f"Rate limit exceeded for {envelope.mail_from} from {client_ip}")
                return '451 4.7.1 Rate limit exceeded. Please try again later.'
            
            # Log email details
            logger.info(f"Relaying email from {envelope.mail_from} to {envelope.rcpt_tos} (client: {client_ip})")
            
            # Send via Microsoft 365
            self._send_via_ms365(envelope)
            
            logger.info(f"Email successfully relayed to Microsoft 365")
            return '250 Message accepted for delivery'
            
        except Exception as e:
            logger.error(f"Error relaying email: {e}", exc_info=True)
            return f'451 Error processing message: {str(e)}'
    
    def _is_sender_allowed(self, sender):
        """Check if sender is in allowed list (deprecated - use Config.is_sender_allowed)"""
        return Config.is_sender_allowed(sender)
    
    def _send_via_ms365(self, envelope):
        """Send email via Microsoft 365 using Graph API"""
        
        # Parse the email message
        msg = BytesParser(policy=default).parsebytes(envelope.content)
        
        # Build the Graph API message payload
        graph_message = self._build_graph_message(msg, envelope)
        
        # Get OAuth2 token
        logger.debug("Acquiring OAuth2 token for Graph API...")
        token = self.oauth.get_access_token()
        
        # Send via Graph API
        logger.debug(f"Sending email via Graph API from {Config.MS365_EMAIL_ADDRESS}")
        
        graph_url = f"{self.oauth.graph_endpoint}/users/{Config.MS365_EMAIL_ADDRESS}/sendMail"
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'message': graph_message,
            'saveToSentItems': 'true'
        }
        
        logger.debug(f"Posting to: {graph_url}")
        logger.debug(f"Headers: Authorization: Bearer [token], Content-Type: application/json")
        logger.debug(f"Payload keys: {list(payload.keys())}")
        
        response = requests.post(graph_url, headers=headers, json=payload, timeout=30)
        
        logger.debug(f"Response status: {response.status_code}")
        logger.debug(f"Response headers: {dict(response.headers)}")
        
        if response.status_code == 202:
            logger.info(f"Email sent successfully via Graph API to {envelope.rcpt_tos}")
        else:
            error_msg = f"Graph API error: {response.status_code} - {response.text}"
            logger.error(error_msg)
            logger.error(f"Request was to: {graph_url}")
            logger.error(f"Message had {len(envelope.rcpt_tos)} recipient(s)")
            raise Exception(error_msg)
    
    def _build_graph_message(self, msg, envelope):
        """Build Graph API message format from email message"""
        
        # Extract headers
        subject = msg.get('Subject', 'No Subject')
        
        # Always use the configured MS365 email address as sender
        # Ignore the MAIL FROM from the client (which is just the SMTP auth user)
        from_email = Config.MS365_EMAIL_ADDRESS
        from_name = Config.MS365_EMAIL_ADDRESS.split('@')[0]
        
        # Build recipient list
        to_recipients = []
        for recipient in envelope.rcpt_tos:
            name, email = parseaddr(recipient)
            to_recipients.append({
                'emailAddress': {
                    'address': email if email else recipient
                }
            })
        
        # Build message body
        graph_msg = {
            'subject': subject,
            'from': {
                'emailAddress': {
                    'address': Config.MS365_EMAIL_ADDRESS
                }
            },
            'toRecipients': to_recipients
        }
        
        # Handle multipart or simple messages
        if msg.is_multipart():
            # Extract parts
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
                    # Handle attachment
                    filename = part.get_filename() or 'attachment'
                    content = part.get_payload(decode=True)
                    if content:
                        attachments.append({
                            '@odata.type': '#microsoft.graph.fileAttachment',
                            'name': filename,
                            'contentType': content_type,
                            'contentBytes': base64.b64encode(content).decode('utf-8')
                        })
            
            # Set body (prefer HTML, fallback to text)
            if html_body:
                graph_msg['body'] = {
                    'contentType': 'HTML',
                    'content': html_body
                }
            elif text_body:
                graph_msg['body'] = {
                    'contentType': 'Text',
                    'content': text_body
                }
            
            # Add attachments
            if attachments:
                graph_msg['attachments'] = attachments
                logger.debug(f"Including {len(attachments)} attachment(s)")
        else:
            # Simple message
            body = msg.get_content()
            content_type = msg.get_content_type()
            
            if content_type == 'text/html':
                graph_msg['body'] = {
                    'contentType': 'HTML',
                    'content': body
                }
            else:
                graph_msg['body'] = {
                    'contentType': 'Text',
                    'content': body
                }
        
        return graph_msg


class AuthenticatedSMTPController(Controller):
    """SMTP Controller with authentication support"""
    
    def __init__(self, handler, tls_context=None, require_starttls=False, ssl_mode=False, **kwargs):
        self.handler_instance = handler
        self.tls_context = tls_context
        self.require_starttls = require_starttls
        self.ssl_mode = ssl_mode  # True for implicit SSL on port 465
        super().__init__(handler, **kwargs)
    
    def factory(self):
        """Create SMTP server instance with authentication"""
        return AuthenticatedSMTP(
            self.handler_instance,
            require_starttls=False,
            tls_context=self.tls_context if not self.ssl_mode else None,
            authenticator=self._authenticate,
            auth_require_tls=False,
            enable_SMTPUTF8=True,
        )
    
    async def _create_server(self, loop):
        """Create the server with optional SSL wrapping"""
        if self.ssl_mode:
            # For SSL mode (port 465), wrap the server with SSL
            return await loop.create_server(
                self.factory,
                host=self.hostname,
                port=self.port,
                ssl=self.tls_context,
            )
        else:
            # For STARTTLS mode (port 587), use regular server
            return await loop.create_server(
                self.factory,
                host=self.hostname,
                port=self.port,
            )
    
    def _run(self, ready_event):
        """Override to support SSL mode"""
        import asyncio
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.loop = loop
        
        try:
            self.server = loop.run_until_complete(self._create_server(loop))
        except Exception as error:
            ready_event.set()
            raise error
        
        ready_event.set()
        
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self.server.close()
            loop.run_until_complete(self.server.wait_closed())
            loop.close()
    
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
