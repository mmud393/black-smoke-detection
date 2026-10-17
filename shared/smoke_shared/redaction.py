"""Secret redaction used by logging and error responses."""

from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_KEY = re.compile(
    r"(pass(word)?|secret|token|api[_-]?key|authorization|cookie|credential|encryption[_-]?key|rtsp[_-]?url)",
    re.IGNORECASE,
)
# scheme://user:pass@host -> scheme://[REDACTED]@host
_URL_CREDS = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://)[^/\s:@]+(?::[^/\s@]*)?@")


def redact_text(text: str) -> str:
    return _URL_CREDS.sub(r"\1" + REDACTED + "@", text)


def redact(value: Any) -> Any:
    """Recursively redact sensitive keys and URL credentials."""
    if isinstance(value, dict):
        return {
            k: REDACTED if isinstance(k, str) and _SENSITIVE_KEY.search(k) else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
