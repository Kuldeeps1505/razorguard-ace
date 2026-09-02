"""
Structured logging setup using structlog.

All logs are JSON in production, pretty-printed in development.
Every log entry carries request_id, session_id, intent_id where available.
NEVER log secrets, API keys, or raw payment credentials.
"""

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

_SENSITIVE_FIELDS = frozenset(
    [
        "password",
        "secret",
        "api_key",
        "razorpay_key_secret",
        "razorpay_webhook_secret",
        "jwt_secret_key",
        "capability_signing_key",
        "app_secret_key",
        "card_number",
        "cvv",
        "upi_pin",
        "anthropic_api_key",
        "openai_api_key",
        "gemini_api_key",
        "groq_api_key",
    ]
)


def _redact_sensitive(logger: WrappedLogger, method: str, event_dict: EventDict) -> EventDict:
    """
    Processor: redact fields that must never appear in logs.
    Add to _SENSITIVE_FIELDS whenever a new sensitive field is introduced.
    """
    for key in list(event_dict.keys()):
        if key.lower() in _SENSITIVE_FIELDS:
            event_dict[key] = "**REDACTED**"
    return event_dict


def configure_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """
    Call once at application startup.

    log_format="json"    → structured JSON (production / staging)
    log_format="console" → human-readable (development)
    """
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        _redact_sensitive,
    ]

    if log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level)

    # Quiet noisy third-party loggers
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a named structured logger."""
    return structlog.get_logger(name)
