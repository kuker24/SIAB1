"""
Structured Logging Configuration
Provides JSON-formatted logging for better log aggregation and analysis.
"""
import logging
import sys
from datetime import datetime
from typing import Any, Dict
from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """
    Custom JSON formatter with additional context fields.
    """

    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: dict):
        """Add custom fields to log record."""
        super().add_fields(log_record, record, message_dict)

        # Add timestamp in ISO format
        log_record['timestamp'] = datetime.utcnow().isoformat()

        # Add log level
        log_record['level'] = record.levelname

        # Add logger name
        log_record['logger'] = record.name

        # Add file info
        log_record['file'] = {
            'name': record.filename,
            'line': record.lineno,
            'function': record.funcName
        }

        # Add process/thread info
        log_record['process_id'] = record.process
        log_record['thread_id'] = record.thread

        # Add exception info if present
        if record.exc_info:
            log_record['exception'] = self.formatException(record.exc_info)


def setup_structured_logging(log_level: str = "INFO", json_logs: bool = True):
    """
    Configure structured logging for the application.

    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_logs: Whether to use JSON formatting (True) or standard format (False)
    """
    # Get root logger
    root_logger = logging.getLogger()

    # Clear existing handlers
    root_logger.handlers = []

    # Set log level
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))

    if json_logs:
        # Use JSON formatter
        formatter = CustomJsonFormatter(
            '%(timestamp)s %(level)s %(logger)s %(message)s'
        )
    else:
        # Use standard formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Suppress noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    return root_logger


class StructuredLogger:
    """
    Wrapper for structured logging with context support.

    Usage:
        logger = StructuredLogger("my_module")
        logger.info("User logged in", user_id=123, ip="192.168.1.1")
    """

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.context = {}

    def set_context(self, **kwargs):
        """Set persistent context fields for all logs."""
        self.context.update(kwargs)

    def clear_context(self):
        """Clear persistent context."""
        self.context = {}

    def _log(self, level: str, message: str, **kwargs):
        """Internal log method with context merging."""
        # Merge persistent context with log-specific context
        log_context = {**self.context, **kwargs}

        # Create extra dict for JSON formatter
        extra = {'context': log_context} if log_context else {}

        # Log with appropriate level
        getattr(self.logger, level)(message, extra=extra)

    def debug(self, message: str, **kwargs):
        """Log debug message with context."""
        self._log('debug', message, **kwargs)

    def info(self, message: str, **kwargs):
        """Log info message with context."""
        self._log('info', message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message with context."""
        self._log('warning', message, **kwargs)

    def error(self, message: str, **kwargs):
        """Log error message with context."""
        self._log('error', message, **kwargs)

    def critical(self, message: str, **kwargs):
        """Log critical message with context."""
        self._log('critical', message, **kwargs)

    def exception(self, message: str, **kwargs):
        """Log exception with context and stack trace."""
        log_context = {**self.context, **kwargs}
        extra = {'context': log_context} if log_context else {}
        self.logger.exception(message, extra=extra)


# Convenience function to create structured loggers
def get_structured_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance."""
    return StructuredLogger(name)


# Example usage patterns
"""
# Basic usage
logger = get_structured_logger(__name__)
logger.info("User login attempt", user_id=123, ip="192.168.1.1")

# With persistent context
logger.set_context(request_id="abc-123", user_id=456)
logger.info("Processing request")  # Will include request_id and user_id
logger.info("Request completed", duration_ms=150)
logger.clear_context()

# Exception logging
try:
    risky_operation()
except Exception as e:
    logger.exception("Operation failed", operation="risky_operation")
"""
