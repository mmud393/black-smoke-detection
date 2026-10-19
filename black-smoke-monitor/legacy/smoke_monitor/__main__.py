"""Entry point: python -m smoke_monitor"""
from __future__ import annotations

import logging
import signal
import sys

from .config import ConfigError, load_config
from .log_setup import setup_logging


def main() -> int:
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    setup_logging(cfg.data_dir, cfg.log_level, cfg.secrets)
    log = logging.getLogger("smoke_monitor")
    from .ai_confirm import ClaudeConfirmer
    from .detector import MotionSmokeDetector
    from .monitor import Monitor

    detector = MotionSmokeDetector(cfg.dark_luminance, cfg.min_blob_fraction, cfg.detection_roi)
    try:
        confirmer = ClaudeConfirmer(cfg.anthropic_api_key, cfg.ai_model, cfg.ai_timeout)
    except Exception as exc:  # no silent fallback: emails need AI confirmation
        log.error("Cannot start AI confirmation: %s", type(exc).__name__)
        return 3
    monitor = Monitor(cfg, detector, confirmer)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: monitor.stop())
    monitor.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
