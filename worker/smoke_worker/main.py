"""Worker entrypoint.

Step 01 scope: the process starts, reports its REAL initialization state and
shuts down cleanly on SIGINT/SIGTERM. It performs no capture, inference or
monitoring, and it says so. It never reports itself as monitoring.
"""

from __future__ import annotations

import logging
import signal
import sys
import threading

from smoke_shared.config import ConfigError, load_settings
from smoke_shared.logging import configure_logging

log = logging.getLogger("worker")


def run(stop: threading.Event | None = None, install_signals: bool = True) -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    configure_logging("worker", settings.log_level)
    stop = stop or threading.Event()

    if install_signals:
        def _handler(signum: int, _frame: object) -> None:
            log.info("shutdown signal received", extra={"signal": signal.Signals(signum).name})
            stop.set()

        signal.signal(signal.SIGINT, _handler)
        signal.signal(signal.SIGTERM, _handler)

    log.info(
        "worker started: idle. No database, cameras or model are wired up yet; "
        "monitoring is NOT active (build step 01).",
        extra={"state": "IDLE_NOT_MONITORING", "monitoring": False},
    )
    stop.wait()
    log.info("worker stopped cleanly", extra={"state": "STOPPED"})
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
