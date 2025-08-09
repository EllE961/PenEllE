"""Core logging module for PenEllE."""

# Import from structured logging module
# Re-export for backward compatibility
import logging

from .structured import (
    LogContext,
    configure_logging,
    configure_module_loggers,
    create_correlation_id,
    get_logger,
    get_request_id,
    get_run_id,
    get_user_id,
    log_with_context,
    set_request_id,
    set_run_id,
    set_user_id,
)

DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL

__all__ = [
    "get_logger",
    "configure_logging",
    "set_request_id",
    "set_run_id",
    "set_user_id",
    "get_request_id",
    "get_run_id",
    "get_user_id",
    "create_correlation_id",
    "LogContext",
    "log_with_context",
    "configure_module_loggers",
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "CRITICAL",
]
