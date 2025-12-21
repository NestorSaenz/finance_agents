"""Structured logging configuration."""

import logging
import sys
from typing import Any

import structlog
from structlog.types import Processor

from .config import settings


def get_log_level() -> int:
    """Get log level based on environment."""
    if settings.ENVIRONMENT == "production":
        return logging.INFO
    return logging.DEBUG


def setup_logging() -> None:
    """Configure structured logging for the application."""

    # Shared processors for all environments
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.ENVIRONMENT == "production":
        # JSON logging for production
        shared_processors.append(structlog.processors.format_exc_info)
        shared_processors.append(structlog.processors.JSONRenderer())
    else:
        # Pretty logging for development
        shared_processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=shared_processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=get_log_level(),
    )

    # Silence noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog logger

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("User logged in", user_id="123")
    """
    return structlog.get_logger(name)


def log_with_context(logger: structlog.stdlib.BoundLogger, **context: Any) -> structlog.stdlib.BoundLogger:
    """Bind additional context to a logger.

    Args:
        logger: Base logger instance
        **context: Key-value pairs to add to log context

    Returns:
        Logger with bound context

    Example:
        >>> logger = get_logger(__name__)
        >>> logger = log_with_context(logger, user_id="123", session_id="abc")
        >>> logger.info("Processing request")  # Will include user_id and session_id
    """
    return logger.bind(**context)
