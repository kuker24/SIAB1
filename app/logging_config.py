"""
Structured JSON Logging Configuration

Provides JSON-formatted logs for Loki/Grafana integration.
Part of Phase 5: Centralized Logging
"""
import logging
import sys
from datetime import datetime, timezone
from typing import Optional
from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with additional fields."""

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)

        # Add timestamp in ISO format
        log_record['timestamp'] = datetime.now(timezone.utc).isoformat()
        log_record['level'] = record.levelname
        log_record['logger'] = record.name

        # Add request context if available
        if hasattr(record, 'request_id'):
            log_record['request_id'] = record.request_id
        if hasattr(record, 'user_id'):
            log_record['user_id'] = record.user_id
        if hasattr(record, 'exam_id'):
            log_record['exam_id'] = record.exam_id


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    json_format: bool = True
):
    """
    Configure application logging.

    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file path for JSON logs
        json_format: Use JSON format (True for production)
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Clear existing handlers
    root_logger.handlers.clear()

    if json_format:
        # JSON formatter for production
        formatter = CustomJsonFormatter(
            '%(timestamp)s %(level)s %(name)s %(message)s'
        )
    else:
        # Human-readable format for development
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (JSON logs for Loki/Promtail)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(CustomJsonFormatter(
            '%(timestamp)s %(level)s %(name)s %(message)s'
        ))
        root_logger.addHandler(file_handler)

    # Reduce noise from third-party libraries
    logging.getLogger('uvicorn').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)

    return root_logger


class LoggerAdapter(logging.LoggerAdapter):
    """Logger adapter with request context."""

    def process(self, msg, kwargs):
        extra = kwargs.get('extra', {})
        extra.update(self.extra)
        kwargs['extra'] = extra
        return msg, kwargs


def get_logger(name: str, request_id: Optional[str] = None, user_id: Optional[int] = None):
    """Get a logger with optional request context."""
    logger = logging.getLogger(name)
    extra = {}
    if request_id:
        extra['request_id'] = request_id
    if user_id:
        extra['user_id'] = user_id
    return LoggerAdapter(logger, extra)
