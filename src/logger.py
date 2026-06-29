"""
Logging configuration for SMTP Relay
"""
import logging
import colorlog
from pathlib import Path
from .config import Config


class _TLSSetupExceptionFilter(logging.Filter):
    """
    Belt-and-suspenders filter on the 'mail.log' logger used by aiosmtpd.
    Downgrades TLSSetupException records to DEBUG so scanner-bot probes
    don't appear as ERROR tracebacks in production logs.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info and record.exc_info[0] is not None:
            try:
                from aiosmtpd.smtp import TLSSetupException
                if issubclass(record.exc_info[0], TLSSetupException):
                    record.levelno = logging.DEBUG
                    record.levelname = 'DEBUG'
            except ImportError:
                pass
        return True


def setup_logging():
    """Setup logging with color output and file logging"""
    
    # Create logs directory if it doesn't exist
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    # Set log level
    log_level = getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO)
    
    # Create logger
    logger = logging.getLogger('smtp_relay')
    logger.setLevel(log_level)
    
    # Remove existing handlers
    logger.handlers = []
    
    # Console handler with color
    console_handler = colorlog.StreamHandler()
    console_handler.setLevel(log_level)
    console_formatter = colorlog.ColoredFormatter(
        '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        }
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler
    file_handler = logging.FileHandler(log_dir / 'smtp_relay.log')
    file_handler.setLevel(log_level)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    return logger

# Create global logger instance
logger = setup_logging()

# Install TLSSetupException filter on aiosmtpd's internal logger
_aiosmtpd_logger = logging.getLogger('mail.log')
if not any(isinstance(f, _TLSSetupExceptionFilter) for f in _aiosmtpd_logger.filters):
    _aiosmtpd_logger.addFilter(_TLSSetupExceptionFilter())
