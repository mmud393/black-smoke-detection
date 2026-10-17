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
    from .detector import GroundingDinoDetector
    from .monitor import Monitor

    try:
        detector = GroundingDinoDetector(cfg.model_local_dir, cfg.detection_prompt,
                                         cfg.box_threshold, cfg.text_threshold, cfg.device)
        detector.warmup()
    except Exception as exc:  # no silent fallback to fake detection
        log.error("Cannot load model: %s: %s", type(exc).__name__, exc)
        return 3
    monitor = Monitor(cfg, detector)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: monitor.stop())
    monitor.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
