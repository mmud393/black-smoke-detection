"""Rotating file + console logging with credential redaction."""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_URL_CREDS = re.compile(r"(rtsp|rtsps|http|https)://[^/\s@]+@", re.IGNORECASE)


class RedactingFilter(logging.Filter):
    """Masks configured secrets and any scheme://user:pass@ fragments in log output."""

    def __init__(self, secrets: list[str] | None = None):
        super().__init__()
        self.secrets = [s for s in (secrets or []) if s and len(s) >= 3]

    def redact(self, text: str) -> str:
        text = _URL_CREDS.sub(lambda m: f"{m.group(1)}://***:***@", text)
        for s in self.secrets:
            text = text.replace(s, "***")
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        record.msg, record.args = self.redact(msg), None
        if record.exc_info:  # fold the traceback in so it is redacted too
            record.exc_text = self.redact(logging.Formatter().formatException(record.exc_info))
        elif record.exc_text:
            record.exc_text = self.redact(record.exc_text)
        return True


def setup_logging(data_dir: Path, level: str = "INFO", secrets: list[str] | None = None,
                  console: bool = True) -> None:
    log_dir = Path(data_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    flt = RedactingFilter(secrets)
    handlers: list[logging.Handler] = [
        RotatingFileHandler(log_dir / "smoke_monitor.log", maxBytes=5_000_000, backupCount=5)
    ]
    if console:
        handlers.append(logging.StreamHandler())
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, level, logging.INFO))
    for h in handlers:
        h.setFormatter(fmt)
        h.addFilter(flt)
        root.addHandler(h)
