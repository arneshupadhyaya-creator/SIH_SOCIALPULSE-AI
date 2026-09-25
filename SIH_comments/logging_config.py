"""
Structured JSON logging via structlog.

Every log line is machine-parseable JSON with a `module` key so you can
filter by component (ingestion, analytics, api, etc.) in log aggregators.
"""

from __future__ import annotations

import logging
import sys

import structlog

from config import get_settings


def setup_logging() -> None:
    """Call once at process startup to wire structlog + stdlib logging."""

    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # ── structlog pipeline ────────────────────────────────────
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # ── Route stdlib logging through structlog so libraries also emit JSON ──
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )


def get_logger(module: str) -> structlog.stdlib.BoundLogger:
    """Return a logger pre-bound with a ``module`` tag.

    Usage::

        log = get_logger("ingestion.client")
        log.info("scrape_started", query="python")
    """
    return structlog.get_logger(module=module)
