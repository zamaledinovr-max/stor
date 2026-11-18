"""Logging configuration with a filter that masks accidental secret leaks."""

from __future__ import annotations

import logging
import re

from app.core.config import Settings

_SECRET_PATTERNS = (
    re.compile(r"(\d{6,12}):[A-Za-z0-9_-]{30,}"),  # bot token
    re.compile(r"(?i)(tma|bearer|token|secret|authorization)([=:\s]+)([^\s,;\"']{8,})"),
)


def redact_secrets(message: str) -> str:
    cleaned = message
    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 3:
            cleaned = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}***", cleaned)
        else:
            cleaned = pattern.sub("bot-token:***", cleaned)
    return cleaned


class SecretRedactionFilter(logging.Filter):
    """Masks bot tokens and Authorization-like values in log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return True
        redacted = redact_secrets(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level, logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
        root.addHandler(handler)
    root.setLevel(level)
    redaction = SecretRedactionFilter()
    for handler in root.handlers:
        if not any(isinstance(item, SecretRedactionFilter) for item in handler.filters):
            handler.addFilter(redaction)
    # Uvicorn access logs contain request lines; the filter above keeps them safe.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "aiogram"):
        logging.getLogger(name).setLevel(level)
