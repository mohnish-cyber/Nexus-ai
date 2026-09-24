"""Secret redaction for logs, audit records and memory filtering."""

from __future__ import annotations

import logging
import re
from typing import Any

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}")),
    ("openai_key", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("aws_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("google_key", re.compile(r"AIza[0-9A-Za-z_\-]{30,}")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
    ("bearer", re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-.=]{16,}")),
]

# Credit-card-like digit runs (validated with Luhn to limit false positives).
_CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_PASSWORD_RE = re.compile(r"(?i)\b(password|passwd|pwd|passcode|pin|otp|cvv|secret)\b\s*(?:is|=|:)\s*\S+")

_SENSITIVE_KEYS = re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd|authorization|cookie|credential)")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def contains_secret(text: str) -> str | None:
    """Return the kind of secret detected in `text`, if any."""
    if not text:
        return None
    for kind, pattern in _PATTERNS:
        if pattern.search(text):
            return kind
    for m in _CARD_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            return "payment_card"
    if _PASSWORD_RE.search(text):
        return "password"
    return None


def redact_text(text: str) -> str:
    if not text:
        return text
    for kind, pattern in _PATTERNS:
        text = pattern.sub(f"[REDACTED:{kind}]", text)

    def _card(m: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            return "[REDACTED:payment_card]"
        return m.group()

    text = _CARD_RE.sub(_card, text)
    text = _PASSWORD_RE.sub(lambda m: f"{m.group(1)}: [REDACTED]", text)
    return text


def redact_value(value: Any, *, max_str: int = 2000) -> Any:
    """Recursively redact a JSON-like structure for safe storage in audit logs."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if isinstance(k, str) and _SENSITIVE_KEYS.search(k):
                out[k] = "[REDACTED]"
            else:
                out[k] = redact_value(v, max_str=max_str)
        return out
    if isinstance(value, list | tuple):
        return [redact_value(v, max_str=max_str) for v in value[:100]]
    if isinstance(value, str):
        v = redact_text(value)
        return v if len(v) <= max_str else v[:max_str] + "…"
    return value


class RedactingFilter(logging.Filter):
    """Logging filter that scrubs secrets from every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # pragma: no cover
            return True
        redacted = redact_text(msg)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True
