"""
SMTP Relay Server Handler
Accepts connections from basic auth and enqueues to Redis for async delivery.
"""
import base64
import asyncio
from aiosmtpd.smtp import SMTP as SMTPServer, Envelope, AuthResult, LoginPassword, TLSSetupException
from aiosmtpd.controller import Controller
from datetime import datetime, timedelta
from collections import defaultdict
from redis import Redis
from rq import Queue
from rq.job import Retry
from .config import Config
from .logger import logger
from .metrics import emails_received, tls_failures, queue_depth
from .worker import send_email_job, on_send_success, on_send_failure


class RateLimiter:
    """Simple rate limiter for email sending"""

    def __init__(self, max_per_minute):
        self.max_per_minute = max_per_minute
        self.requests = defaultdict(list)

    def is_allowed(self, identifier):
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        self.requests[identifier] = [
            t for t in self.requests[identifier] if t > minute_ago
        ]
        if len(self.requests[identifier]) >= self.max_per_minute:
            return False
        self.requests[identifier].append(now)
        return True


class SMTPRelayHandler:
    """SMTP handler that accepts emails and enqueues them for async delivery via RQ."""

    def __init__(self):
        self.rate_limiter = RateLimiter(Config.RATE_LIMIT_PER_MINUTE)
        self._redis = Redis.from_url(Config.REDIS_URL)
        self._queue = Queue('email', connection=self._redis)

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        peer = session.peer
        client_ip = peer[0] if peer else 'unknown'

        if not Config.is_ip_allowed(client_ip):
            logger.warning(f'Rejected connection from unauthorized IP: {client_ip}')
            return '550 5.7.1 Connection from this IP address not allowed'

        if not Config.is_sender_allowed(envelope.mail_from):
            logger.warning(f'Rejected email from unauthorized sender: {envelope.mail_from} (IP: {client_ip})')
            return '550 5.7.1 Sender not allowed'

        envelope.rcpt_tos.append(address)
        logger.debug(f'Accepted recipient: {address} from {client_ip}')
        return '250 OK'

    async def handle_DATA(self, server, session, envelope):
        peer = session.peer
        client_ip = peer[0] if peer else 'unknown'

        if not self.rate_limiter.is_allowed(envelope.mail_from):
            logger.warning(f'Rate limit exceeded for {envelope.mail_from} from {client_ip}')
            return '451 4.7.1 Rate limit exceeded. Please try again later.'

        try:
            content_b64 = base64.b64encode(envelope.content).decode('utf-8')

            job = self._queue.enqueue(
                send_email_job,
                args=(content_b64, envelope.mail_from, list(envelope.rcpt_tos)),
                retry=Retry(
                    max=Config.RQ_MAX_RETRIES,
                    interval=Config.RQ_RETRY_INTERVALS,
                ),
                on_success=on_send_success,
                on_failure=on_send_failure,
                job_timeout=120,
            )

            emails_received.labels(from_ip=client_ip).inc()
            queue_depth.set(self._queue.count)
            logger.info(
                f'Email queued as job {job.id} '
                f'from {envelope.mail_from} to {envelope.rcpt_tos} '
                f'(client: {client_ip})'
            )
            return '250 Message accepted for delivery'

        except Exception as e:
            logger.error(f'Failed to enqueue email: {e}', exc_info=True)
            return '451 4.3.0 Temporary queue unavailable, please retry'

    async def handle_exception(self, error: Exception) -> str:
        """Intercepts session-level exceptions. Suppresses TLSSetupException
        from scanner bots so they don't pollute logs as ERROR tracebacks."""
        if isinstance(error, TLSSetupException):
            tls_failures.inc()
            logger.debug(f'TLS handshake aborted by remote peer (scanner probe): {error}')
            return '421 4.7.0 TLS handshake failed'
        logger.error(f'SMTP session exception: {error}', exc_info=True)
        return f'500 Error: ({type(error).__name__}) {error}'


class AuthenticatedSMTPController(Controller):
    """SMTP Controller with authentication support for STARTTLS"""

    def __init__(self, handler, tls_context=None, require_starttls=False, **kwargs):
        self.handler_instance = handler
        self.tls_context = tls_context
        self.require_starttls = require_starttls
        self.auth_require_tls = require_starttls
        super().__init__(handler, **kwargs)

    def factory(self):
        return AuthenticatedSMTP(
            self.handler_instance,
            require_starttls=self.require_starttls,
            tls_context=self.tls_context,
            authenticator=self._authenticate,
            auth_require_tls=self.auth_require_tls,
            enable_SMTPUTF8=True,
        )

    def _authenticate(self, server, session, envelope, mechanism, auth_data):
        fail_nothandled = AuthResult(success=False, handled=False)

        if mechanism not in ('LOGIN', 'PLAIN'):
            return fail_nothandled

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
                else:
                    try:
                        s = auth_data.decode('utf-8', errors='ignore')
                        parts = s.split('\0')
                        if len(parts) == 3:
                            username = parts[1]
                            password = parts[2]
                    except Exception:
                        pass
            elif isinstance(auth_data, str):
                parts = auth_data.split('\0')
                if len(parts) == 3:
                    username = parts[1]
                    password = parts[2]
        except Exception as e:
            logger.exception(f'Error parsing auth_data: {e}')
            return AuthResult(success=False, handled=True)

        if username is None or password is None:
            logger.warning('Authentication data in unexpected format')
            return fail_nothandled

        if username == Config.SMTP_RELAY_USERNAME and password == Config.SMTP_RELAY_PASSWORD:
            logger.info(f'Successful authentication for user: {username}')
            return AuthResult(success=True, handled=True)
        else:
            logger.warning(f'Failed authentication attempt for user: {username}')
            return AuthResult(success=False, handled=True)


class SSLSMTPController(Controller):
    """SMTP Controller with implicit SSL support (port 465)"""

    def __init__(self, handler, tls_context=None, **kwargs):
        self.handler_instance = handler
        self.tls_context = tls_context
        super().__init__(handler, ssl_context=tls_context, **kwargs)

    def factory(self):
        return AuthenticatedSMTP(
            self.handler_instance,
            require_starttls=False,
            tls_context=None,
            authenticator=self._authenticate,
            auth_require_tls=False,
            enable_SMTPUTF8=True,
        )

    def _authenticate(self, server, session, envelope, mechanism, auth_data):
        fail_nothandled = AuthResult(success=False, handled=False)

        if mechanism not in ('LOGIN', 'PLAIN'):
            return fail_nothandled

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
                else:
                    try:
                        s = auth_data.decode('utf-8', errors='ignore')
                        parts = s.split('\0')
                        if len(parts) == 3:
                            username = parts[1]
                            password = parts[2]
                    except Exception:
                        pass
            elif isinstance(auth_data, str):
                parts = auth_data.split('\0')
                if len(parts) == 3:
                    username = parts[1]
                    password = parts[2]
        except Exception as e:
            logger.exception(f'Error parsing auth_data: {e}')
            return AuthResult(success=False, handled=True)

        if username is None or password is None:
            logger.warning('Authentication data in unexpected format')
            return fail_nothandled

        if username == Config.SMTP_RELAY_USERNAME and password == Config.SMTP_RELAY_PASSWORD:
            logger.info(f'Successful authentication for user: {username}')
            return AuthResult(success=True, handled=True)
        else:
            logger.warning(f'Failed authentication attempt for user: {username}')
            return AuthResult(success=False, handled=True)


class AuthenticatedSMTP(SMTPServer):
    """Custom SMTP server with authentication"""

    def __init__(self, handler, **kwargs):
        self.handler_instance = handler
        super().__init__(handler, **kwargs)


# Belt-and-suspenders: also suppress TLSSetupException in the aiosmtpd logger
# in case any code path bypasses handle_exception.
import logging as _logging

try:
    class _TLSFilter(_logging.Filter):
        def filter(self, record):
            if record.exc_info and record.exc_info[0] is TLSSetupException:
                tls_failures.inc()
                logger.debug('TLS handshake aborted by remote peer (scanner probe)')
                return False
            return True

    _logging.getLogger('mail.log').addFilter(_TLSFilter())
except Exception:
    pass
