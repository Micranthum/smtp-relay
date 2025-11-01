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
from .relay import SMTPRelayHandler, AuthenticatedSMTPController

class SMTPRelayServer:
    """Main SMTP Relay Server"""
    
    def __init__(self):
        self.controller = None
        
    def start(self):
        """Start the SMTP relay server"""
        try:
            # Validate configuration
            logger.info("Validating configuration...")
            Config.validate()
            logger.info("Configuration validated successfully")
            
            # Log environment info
            logger.info(f"Environment: {Config.ENVIRONMENT}")
            logger.info(f"Encryption Mode: {Config.SMTP_ENCRYPTION_MODE}")
            logger.info(f"TLS Enabled: {Config.SMTP_RELAY_USE_TLS}")
            logger.info(f"IP Whitelist: {Config.ALLOWED_IPS}")
            logger.info(f"Sender Whitelist: {Config.ALLOWED_SENDERS}")
            logger.info(f"Rate Limit: {Config.RATE_LIMIT_PER_MINUTE} emails/minute")
            
            # Create TLS context based on encryption mode
            tls_context = None
            require_starttls = False
            
            if Config.SMTP_ENCRYPTION_MODE == 'SSL':
                # SSL mode: implicit TLS from connection start (like port 465)
                try:
                    tls_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                    tls_context.load_cert_chain(
                        certfile=Config.TLS_CERT_FILE,
                        keyfile=Config.TLS_KEY_FILE
                    )
                    require_starttls = False  # No STARTTLS command, TLS is implicit
                    logger.info("✅ SSL mode: TLS context created (implicit TLS)")
                except Exception as e:
                    logger.error(f"❌ Failed to create TLS context for SSL mode: {e}")
                    raise
                    
            elif Config.SMTP_ENCRYPTION_MODE == 'STARTTLS':
                # STARTTLS mode: optional upgrade to TLS after connection
                if Config.SMTP_RELAY_USE_TLS:
                    try:
                        tls_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                        tls_context.load_cert_chain(
                            certfile=Config.TLS_CERT_FILE,
                            keyfile=Config.TLS_KEY_FILE
                        )
                        require_starttls = False  # Don't require, but offer STARTTLS
                        logger.info("✅ STARTTLS mode: TLS context created (optional upgrade)")
                    except Exception as e:
                        logger.error(f"❌ Failed to create TLS context for STARTTLS mode: {e}")
                        raise
                else:
                    logger.info("⚠️  STARTTLS mode: TLS disabled (plain text connections)")
                    
            elif Config.SMTP_ENCRYPTION_MODE == 'NONE':
                # No encryption
                logger.warning("⚠️  WARNING: No encryption enabled - connections will be in plain text!")
                logger.warning("⚠️  This is NOT recommended for production use!")
            
            # Create handler
            handler = SMTPRelayHandler()
            
            # Create controller
            self.controller = AuthenticatedSMTPController(
                handler,
                hostname=Config.SMTP_RELAY_HOST,
                port=Config.SMTP_RELAY_PORT,
                tls_context=tls_context,
                require_starttls=require_starttls,
            )
            
            # Start server
            logger.info(f"Starting SMTP Relay Server on {Config.SMTP_RELAY_HOST}:{Config.SMTP_RELAY_PORT}")
            logger.info(f"Relay target: Microsoft Graph API")
            logger.info(f"Using email address: {Config.MS365_EMAIL_ADDRESS}")
            
            self.controller.start()
            
            logger.info("SMTP Relay Server started successfully")
            logger.info("Ready to accept connections from Contpaq")
            
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
        if self.controller:
            logger.info("Stopping SMTP Relay Server...")
            self.controller.stop()
            logger.info("Server stopped")


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
