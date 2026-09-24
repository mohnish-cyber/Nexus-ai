"""Logging with automatic secret redaction."""

from __future__ import annotations

import logging
import sys

from app.security.redaction import RedactingFilter


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    if not any(isinstance(h, logging.StreamHandler) and getattr(h, "_nexus", False) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
        handler._nexus = True  # type: ignore[attr-defined]
        handler.addFilter(RedactingFilter())
        root.addHandler(handler)
    for noisy in ("httpx", "httpcore", "anthropic", "watchfiles", "aiosqlite"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
