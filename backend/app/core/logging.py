"""Centralized logging configuration for the application."""

import logging
import logging.handlers
import sys
from datetime import datetime

from .paths import get_logs_dir

LOG_DIR = get_logs_dir()

# Log file path with timestamp
LOG_FILE = LOG_DIR / f"app-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"

# Format with timestamp, logger name, level, and message
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: int = logging.INFO) -> None:
    """Configure logging for the entire application.
    
    Args:
        level: Logging level (default: INFO)
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid UnicodeEncodeError on Windows consoles (cp1252) when logs contain
    # non-ASCII transcript text from speech recognition.
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        # Continue with default streams if reconfigure is unavailable.
        pass
    
    # Remove any existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    
    # Console handler (stdout)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (rotating, max 10MB per file, keep 5 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Suppress verbose third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    
    # Log startup
    root_logger.info(f"Logging configured (level={logging.getLevelName(level)}, file={LOG_FILE})")


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a module.
    
    Args:
        name: Module name (typically __name__)
    
    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


def log_exception(logger: logging.Logger, event: str, exc: BaseException, **context: object) -> None:
    """Log an exception with consistent structured context."""
    context_bits = " ".join(f"{key}={value}" for key, value in context.items())
    message = event if not context_bits else f"{event} {context_bits}"
    logger.exception(
        "%s exception_type=%s error=%s",
        message,
        type(exc).__name__,
        exc,
    )
