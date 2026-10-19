"""Manually run: python -m smoke_monitor.test_email  (sends ONE clearly marked test message)."""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from .config import ConfigError, load_config
from .email_alert import build_message, smtp_send


def main() -> int:
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(exc)
        return 2
    try:
        smtp_send(cfg, build_message(cfg, None, datetime.now(timezone.utc), test=True))
    except Exception as exc:  # noqa: BLE001
        print(f"Test email FAILED: {type(exc).__name__}: {str(exc).replace(cfg.smtp_password, '***')}")
        return 1
    print(f"Test email accepted by SMTP server for {', '.join(cfg.alert_to)} "
          "(inbox delivery not confirmed).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
