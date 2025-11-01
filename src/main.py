"""
SMTP Relay Server - Main Entry Point
Bridges Contpaq (Basic Auth) with Microsoft 365 (OAuth2)
"""
import asyncio
import signal
import sys
import ssl
from .config import Config
from .logger import logger
from .relay import SMTPRelayHandler, AuthenticatedSMTPController, SSLSMTPController

class SMTPRelayServer:
    """Main SMTP Relay Server"""
    
    def __init__(self):
        self.controller_starttls = None
        self.controller_ssl = None
        
    def start(self):
        """Start the SMTP relay server"""
        try:
            # Validate configuration
            logger.info("Validating configuration...")
            Config.validate()
            logger.info("Configuration validated successfully")
            
            # Log environment info
            logger.info(f"Environment: {Config.ENVIRONMENT}")
            logger.info(f"TLS Enabled: {Config.SMTP_RELAY_USE_TLS}")
            logger.info(f"IP Whitelist: {Config.ALLOWED_IPS}")
            logger.info(f"Sender Whitelist: {Config.ALLOWED_SENDERS}")
            logger.info(f"Rate Limit: {Config.RATE_LIMIT_PER_MINUTE} emails/minute")
            
            # Create TLS context if enabled
            tls_context = None
            if Config.SMTP_RELAY_USE_TLS:
                logger.info("Creating TLS context...")
                try:
                    tls_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                    tls_context.load_cert_chain(
                        certfile=Config.TLS_CERT_FILE,
                        keyfile=Config.TLS_KEY_FILE
                    )
                    logger.info("Success: TLS context created successfully")
                except Exception as e:
                    logger.error(f"Error: Failed to create TLS context: {e}")
                    raise
            else:
                logger.warning("TLS is DISABLED - connections will NOT be encrypted!")
            
            # Create handlers for both servers
            handler_starttls = SMTPRelayHandler()
            handler_ssl = SMTPRelayHandler()
            
            # Create STARTTLS controller (port 587)
            logger.info(f"Setting up STARTTLS server on port {Config.SMTP_STARTTLS_PORT}...")
            # In production with TLS, require STARTTLS; in development allow plain connections
            require_starttls = Config.SMTP_RELAY_USE_TLS and Config.ENVIRONMENT == 'production'
            if require_starttls:
                logger.info("  STARTTLS will be REQUIRED for all connections")
            else:
                logger.info("  STARTTLS is OPTIONAL (development mode or TLS disabled)")
            
            self.controller_starttls = AuthenticatedSMTPController(
                handler_starttls,
                hostname=Config.SMTP_RELAY_HOST,
                port=Config.SMTP_STARTTLS_PORT,
                tls_context=tls_context,
                require_starttls=require_starttls,
            )
            
            # Create SSL/TLS controller (port 465) with implicit TLS
            logger.info(f"Setting up SSL server on port {Config.SMTP_SSL_PORT} (implicit TLS)...")
            self.controller_ssl = SSLSMTPController(
                handler_ssl,
                hostname=Config.SMTP_RELAY_HOST,
                port=Config.SMTP_SSL_PORT,
                tls_context=tls_context,
            )
            
            # Start servers
            logger.info("=" * 70)
            logger.info(f"Starting SMTP Relay Servers:")
            logger.info(f"STARTTLS on {Config.SMTP_RELAY_HOST}:{Config.SMTP_STARTTLS_PORT} (TLS: {'enabled' if tls_context else 'disabled'})")
            logger.info(f"SSL/TLS on {Config.SMTP_RELAY_HOST}:{Config.SMTP_SSL_PORT} (TLS: {'enabled' if tls_context else 'disabled'})")
            logger.info(f"Relay target: Microsoft Graph API")
            logger.info(f"Using email address: {Config.MS365_EMAIL_ADDRESS}")
            logger.info("=" * 70)
            
            self.controller_starttls.start()
            self.controller_ssl.start()

            logger.info("Success: Both SMTP servers started")
            if tls_context:
                logger.info("Ready to accept secure connections:")
                logger.info("  - Modern clients: use port 587 with STARTTLS")
                logger.info("  - Legacy clients: use port 465 with SSL/TLS")
            else:
                logger.warning("Ready to accept INSECURE connections (TLS disabled):")
                logger.warning("  - Port 587 (STARTTLS available but optional)")
                logger.warning("  - Port 465 (no encryption)")
            
            # Keep running
            try:
                asyncio.get_event_loop().run_forever()
            except KeyboardInterrupt:
                logger.info("Received shutdown signal")
                self.stop()
                
        except ValueError as e:
            logger.error(f"Configuration error: {e}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Failed to start server: {e}", exc_info=True)
            sys.exit(1)
    
    def stop(self):
        """Stop the SMTP relay server"""
        logger.info("Stopping SMTP Relay Servers...")
        if self.controller_starttls:
            self.controller_starttls.stop()
            logger.info("STARTTLS server stopped")
        if self.controller_ssl:
            self.controller_ssl.stop()
            logger.info("SSL server stopped")
        logger.info("All servers stopped")


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}")
    sys.exit(0)


def main():
    """Main entry point"""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Print banner
    logger.info("=" * 60)
    logger.info("SMTP Relay Server - Contpaq to Microsoft 365")
    logger.info("Bridging Basic Auth to OAuth2")
    logger.info("=" * 60)
    
    # Start server
    server = SMTPRelayServer()
    server.start()


if __name__ == '__main__':
    main()
