"""Structured logging.

JSON in production (so log aggregators can parse it), coloured console in local
development. Every event carries the request id bound by the middleware in
`main.py`, which is what makes one slow request traceable end to end.
"""

import logging
import sys
from typing import Any

import structlog

from config import settings

# Third-party loggers are noisy at INFO and duplicate our own structured events.
_NOISY_LOGGERS = ("uvicorn.access", "sqlalchemy.engine", "httpx", "httpcore")


def configure_logging() -> None:
    """Install structlog + stdlib logging configuration. Idempotent."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    renderer: Any
    if settings.is_production:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            # Pulls anything bound via structlog.contextvars (e.g. request_id)
            # into the event dict, so every log line is correlatable.
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


log = structlog.get_logger()

__all__ = ["configure_logging", "log"]
