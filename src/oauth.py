"""
Microsoft 365 OAuth2 authentication handler
"""
import msal
from datetime import datetime, timedelta
from redis import Redis
from .config import Config
from .logger import logger

REDIS_TOKEN_KEY = 'smtp_relay:ms365_access_token'


class MS365OAuth:
    """Handle OAuth2 authentication with Microsoft 365"""

    def __init__(self):
        self.tenant_id = Config.GRAPH_API_TENANT_ID
        self.client_id = Config.GRAPH_API_CLIENT_ID
        self.client_secret = Config.GRAPH_API_CLIENT_SECRET
        self.email_address = Config.MS365_EMAIL_ADDRESS

        # OAuth2 scopes for Microsoft Graph API (using Mail.Send application permission)
        self.scopes = [Config.GRAPH_API_SCOPE]

        # Authority URL
        self.authority = f'{Config.GRAPH_API_AUTHORITY_BASE}/{self.tenant_id}'

        # Graph API endpoint
        self.graph_endpoint = Config.GRAPH_API_ENDPOINT

        # Token cache — Redis, shared across worker processes/replicas
        self._redis = Redis.from_url(Config.REDIS_URL)

        # MSAL app
        self.app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=self.authority,
            client_credential=self.client_secret,
        )

        self._cached_token = None
        self._token_expiry = None

    def get_access_token(self):
        """Get a valid access token, using cache if available"""

        # Check if in-memory cached token is still valid (avoids a Redis round-trip)
        if self._is_token_valid():
            logger.debug("Using cached access token")
            return self._cached_token

        # Try to load from Redis (shared across worker processes)
        if self._load_token_from_redis():
            logger.debug("Using token from Redis cache")
            return self._cached_token

        # Acquire new token
        logger.info("Acquiring new access token from Microsoft 365")
        logger.debug(f"Using authority: {self.authority}")
        logger.debug(f"Using scopes: {self.scopes}")
        logger.debug(f"Using client_id: {self.client_id[:8]}...")

        result = self.app.acquire_token_for_client(scopes=self.scopes)

        if 'access_token' in result:
            self._cached_token = result['access_token']
            # Set expiry time (usually 1 hour, but we'll refresh 5 min before)
            expires_in = result.get('expires_in', 3600)
            self._token_expiry = datetime.now() + timedelta(seconds=expires_in - 300)

            self._save_token_to_redis(self._cached_token, expires_in)

            logger.info(f"Successfully acquired access token (expires in {expires_in}s)")
            logger.debug(f"Token type: {result.get('token_type', 'N/A')}")
            return self._cached_token
        else:
            error = result.get('error', 'Unknown error')
            error_desc = result.get('error_description', 'No description')
            logger.error(f"Failed to acquire token: {error} - {error_desc}")
            raise Exception(f"OAuth2 authentication failed: {error} - {error_desc}")

    def _is_token_valid(self):
        """Check if current in-memory token is valid"""
        if not self._cached_token or not self._token_expiry:
            return False
        return datetime.now() < self._token_expiry

    def _save_token_to_redis(self, token, expires_in):
        """Cache the token in Redis with a TTL — lets Redis handle expiry directly"""
        try:
            ttl = max(expires_in - 300, 1)
            self._redis.setex(REDIS_TOKEN_KEY, ttl, token)
            logger.debug(f"Token cached in Redis (ttl={ttl}s)")
        except Exception as e:
            logger.warning(f"Failed to cache token in Redis: {e}")

    def _load_token_from_redis(self):
        """Load token from Redis cache, if present (Redis TTL guarantees it's not expired)"""
        try:
            token = self._redis.get(REDIS_TOKEN_KEY)
            if not token:
                return False
            ttl = self._redis.ttl(REDIS_TOKEN_KEY)
            if ttl <= 0:
                return False
            self._cached_token = token.decode('utf-8')
            self._token_expiry = datetime.now() + timedelta(seconds=ttl)
            return True
        except Exception as e:
            logger.warning(f"Failed to load token from Redis: {e}")
            return False

    def get_oauth_string(self):
        """Generate OAuth2 string for SMTP authentication"""
        token = self.get_access_token()
        # Format: user=username^Aauth=Bearer token^A^A
        # ^A is \x01 (ASCII 1)
        oauth_string = f"user={self.email_address}\x01auth=Bearer {token}\x01\x01"
        return oauth_string
