"""
Microsoft 365 OAuth2 authentication handler
"""
import json
import msal
from pathlib import Path
from datetime import datetime, timedelta
from .config import Config
from .logger import logger

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
        
        # Token cache file
        self.token_cache_file = Path('token_cache') / 'ms365_token.json'
        self.token_cache_file.parent.mkdir(exist_ok=True)
        
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
        
        # Check if cached token is still valid
        if self._is_token_valid():
            logger.debug("Using cached access token")
            return self._cached_token
        
        # Try to load from file cache
        if self._load_token_from_file():
            if self._is_token_valid():
                logger.debug("Using token from file cache")
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
            
            # Save to file cache
            self._save_token_to_file(result)
            
            logger.info(f"Successfully acquired access token (expires in {expires_in}s)")
            logger.debug(f"Token type: {result.get('token_type', 'N/A')}")
            return self._cached_token
        else:
            error = result.get('error', 'Unknown error')
            error_desc = result.get('error_description', 'No description')
            logger.error(f"Failed to acquire token: {error} - {error_desc}")
            raise Exception(f"OAuth2 authentication failed: {error} - {error_desc}")
    
    def _is_token_valid(self):
        """Check if current token is valid"""
        if not self._cached_token or not self._token_expiry:
            return False
        return datetime.now() < self._token_expiry
    
    def _save_token_to_file(self, token_response):
        """Save token to file cache with secure permissions"""
        try:
            cache_data = {
                'access_token': token_response['access_token'],
                'expires_in': token_response.get('expires_in', 3600),
                'timestamp': datetime.now().isoformat(),
            }
            
            # Write with restrictive permissions
            self.token_cache_file.parent.mkdir(mode=0o700, exist_ok=True)
            
            # Write atomically using temp file
            temp_file = self.token_cache_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(cache_data, f)
            
            # Set restrictive permissions before moving
            temp_file.chmod(0o600)
            
            # Atomic rename
            temp_file.replace(self.token_cache_file)
            
            logger.debug("Token saved to file cache with secure permissions (0600)")
        except Exception as e:
            logger.warning(f"Failed to save token to cache: {e}")
    
    def _load_token_from_file(self):
        """Load token from file cache"""
        try:
            if not self.token_cache_file.exists():
                return False
            
            with open(self.token_cache_file, 'r') as f:
                cache_data = json.load(f)
            
            timestamp = datetime.fromisoformat(cache_data['timestamp'])
            expires_in = cache_data['expires_in']
            expiry_time = timestamp + timedelta(seconds=expires_in - 300)
            
            if datetime.now() < expiry_time:
                self._cached_token = cache_data['access_token']
                self._token_expiry = expiry_time
                return True
            else:
                logger.debug("Cached token has expired")
                return False
                
        except Exception as e:
            logger.warning(f"Failed to load token from cache: {e}")
            return False
    
    def get_oauth_string(self):
        """Generate OAuth2 string for SMTP authentication"""
        token = self.get_access_token()
        # Format: user=username^Aauth=Bearer token^A^A
        # ^A is \x01 (ASCII 1)
        oauth_string = f"user={self.email_address}\x01auth=Bearer {token}\x01\x01"
        return oauth_string
