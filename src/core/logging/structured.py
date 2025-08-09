"""Structured logging implementation for PenEllE.

This module provides JSON-formatted structured logging with:
- Correlation IDs for request tracing
- Context-aware logging
- Integration with the event system
- Configurable log levels per module
"""

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any, Dict, List, Optional, Union

import structlog
from structlog.processors import (
    CallsiteParameter,
    CallsiteParameterAdder,
    JSONRenderer,
    KeyValueRenderer,
    StackInfoRenderer,
    TimeStamper,
    UnicodeDecoder,
    add_log_level,
)
from structlog.stdlib import LoggerFactory

# Avoid circular import - config loader will be imported when needed
# from src.core.config import get_config_loader

# Context variables for request tracking
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
run_id_var: ContextVar[Optional[str]] = ContextVar("run_id", default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default=None)


def set_request_id(request_id: str) -> None:
    """Set the current request ID for logging context."""
    request_id_var.set(request_id)


def set_run_id(run_id: str) -> None:
    """Set the current pipeline run ID for logging context."""
    run_id_var.set(run_id)


def set_user_id(user_id: str) -> None:
    """Set the current user ID for logging context."""
    user_id_var.set(user_id)


def get_request_id() -> Optional[str]:
    """Get the current request ID."""
    return request_id_var.get()


def get_run_id() -> Optional[str]:
    """Get the current pipeline run ID."""
    return run_id_var.get()


def get_user_id() -> Optional[str]:
    """Get the current user ID."""
    return user_id_var.get()


class ContextualProcessor:
    """Add contextual information to log entries."""

    def __call__(self, logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Add context variables to the event dict."""
        # Add correlation IDs
        if request_id := get_request_id():
            event_dict["request_id"] = request_id
        if run_id := get_run_id():
            event_dict["run_id"] = run_id
        if user_id := get_user_id():
            event_dict["user_id"] = user_id

        # Add service info
        event_dict["service"] = "penelle"
        event_dict["environment"] = self._get_environment()

        return event_dict

    def _get_environment(self) -> str:
        """Get current environment from config."""
        try:
            # Lazy import to avoid circular dependency
            from src.core.config import get_config_loader

            config = get_config_loader().load_config("deployment")
            return str(config.get("environment", "local"))
        except Exception:
            return "local"


class ErrorDetailsProcessor:
    """Add detailed error information to log entries."""

    def __call__(self, logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Add error details if exception info is present."""
        if "exc_info" in event_dict and event_dict["exc_info"]:
            exc_info = event_dict["exc_info"]
            if isinstance(exc_info, tuple) and len(exc_info) >= 2:
                exc_type, exc_value, _ = exc_info
                event_dict["error_type"] = exc_type.__name__ if exc_type else "Unknown"
                event_dict["error_message"] = str(exc_value) if exc_value else ""

        return event_dict


class SensitiveDataFilter:
    """Filter sensitive data from log entries."""

    SENSITIVE_KEYS = {
        "password",
        "token",
        "api_key",
        "secret",
        "authorization",
        "private_key",
        "access_token",
        "refresh_token",
        "credential",
    }

    def __call__(self, logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Filter sensitive data from the event dict."""
        self._filter_dict(event_dict)
        return event_dict

    def _filter_dict(self, d: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively filter sensitive data from a dictionary."""
        for key in list(d.keys()):
            if any(sensitive in key.lower() for sensitive in self.SENSITIVE_KEYS):
                d[key] = "[REDACTED]"
            elif isinstance(d[key], dict):
                self._filter_dict(d[key])
            elif isinstance(d[key], list):
                for item in d[key]:
                    if isinstance(item, dict):
                        self._filter_dict(item)
        return d


def configure_logging(
    log_level: str = "INFO",
    log_format: str = "json",
    log_file: Optional[str] = None,
    enable_console: bool = True,
) -> None:
    """Configure structured logging for the application.

    Args:
        log_level: Default log level
        log_format: Output format ('json' or 'console')
        log_file: Optional log file path
        enable_console: Whether to log to console
    """
    # Convert log level string to logging constant
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Configure processors
    timestamper = TimeStamper(fmt="iso", utc=True)

    shared_processors = [
        timestamper,
        add_log_level,
        ContextualProcessor(),
        ErrorDetailsProcessor(),
        SensitiveDataFilter(),
        CallsiteParameterAdder(
            parameters=[
                CallsiteParameter.FILENAME,
                CallsiteParameter.LINENO,
                CallsiteParameter.FUNC_NAME,
            ]
        ),
        StackInfoRenderer(),
        UnicodeDecoder(),
    ]

    # Choose renderer based on format
    renderer: Union[JSONRenderer, KeyValueRenderer]
    if log_format == "json":
        renderer = JSONRenderer(sort_keys=True)
    else:
        renderer = KeyValueRenderer(key_order=["timestamp", "level", "event"])

    processors: Any = shared_processors + [renderer]

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard logging
    handlers: List[logging.Handler] = []

    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        handlers.append(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        handlers.append(file_handler)

    logging.basicConfig(
        level=level,
        handlers=handlers,
        format="%(message)s",
    )

    # Suppress noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured logger instance
    """
    return structlog.get_logger(name)  # type: ignore


def log_with_context(
    logger: structlog.BoundLogger, level: str, message: str, **kwargs: Any
) -> None:
    """Log a message with additional context.

    Args:
        logger: Logger instance
        level: Log level
        message: Log message
        **kwargs: Additional context fields
    """
    log_method = getattr(logger, level.lower())
    log_method(message, **kwargs)


def create_correlation_id() -> str:
    """Create a new correlation ID for request tracking.

    Returns:
        UUID string for correlation
    """
    return str(uuid.uuid4())


class LogContext:
    """Context manager for temporary logging context."""

    def __init__(self, **kwargs: Any) -> None:
        """Initialize with context fields to add."""
        self.context = kwargs
        self.tokens: List[Any] = []

    def __enter__(self) -> "LogContext":
        """Enter context and set context variables."""
        for key, value in self.context.items():
            if key == "request_id":
                self.tokens.append(request_id_var.set(value))
            elif key == "run_id":
                self.tokens.append(run_id_var.set(value))
            elif key == "user_id":
                self.tokens.append(user_id_var.set(value))
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context and reset context variables."""
        for token in self.tokens:
            token.var.reset(token)


# Module-level logger configuration
def configure_module_loggers(config: Dict[str, str]) -> None:
    """Configure log levels for specific modules.

    Args:
        config: Dictionary mapping module names to log levels

    Example:
        configure_module_loggers({
            "src.pipeline": "DEBUG",
            "src.llm": "INFO",
            "src.database": "WARNING"
        })
    """
    for module_name, level_str in config.items():
        level = getattr(logging, level_str.upper(), logging.INFO)
        logging.getLogger(module_name).setLevel(level)


# Initialize logging on module import
def initialize_logging() -> None:
    """Initialize logging with configuration from file or defaults."""
    try:
        # Try to load config - lazy import to avoid circular dependency
        from src.core.config import get_config_loader

        config = get_config_loader().load_config("deployment")
        log_config = config.get("logging", {})

        configure_logging(
            log_level=log_config.get("level", "INFO"),
            log_format=log_config.get("format", "json"),
            log_file=log_config.get("file"),
            enable_console=log_config.get("console", True),
        )

        # Configure module-specific levels
        if module_levels := log_config.get("module_levels"):
            configure_module_loggers(module_levels)

    except Exception:
        # Fall back to defaults if config fails
        configure_logging()


# Auto-initialize if imported
initialize_logging()
