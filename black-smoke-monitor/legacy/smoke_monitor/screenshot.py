"""Annotated JPEG evidence, written atomically, with retention cleanup."""
from __future__ import annotations

import logging
import secrets
import time
from datetime import datetime, timezone, tzinfo
from pathlib import Path

import cv2
import numpy as np

from .state import atomic_write_bytes

log = logging.getLogger(__name__)


def save_screenshot(frame: np.ndarray, box, out_dir: Path, tz: tzinfo,
                    camera_name: str = "", now: datetime | None = None) -> Path:
    """Draw the rectangle + timestamp and save black_smoke_YYYYMMDD_HHMMSS_<id>.jpg."""
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(tz)
    img = frame.copy()
    x1, y1, x2, y2 = box
    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 3)
    label = f"{camera_name} {local:%Y-%m-%d %H:%M:%S %Z} | UTC {now:%H:%M:%S}".strip()
    cv2.rectangle(img, (0, 0), (min(img.shape[1], 14 * len(label) // 2 + 20), 34), (0, 0, 0), -1)
    cv2.putText(img, label, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    name = f"black_smoke_{now:%Y%m%d_%H%M%S}_{secrets.token_hex(3)}.jpg"
    path = Path(out_dir) / name  # name is generated, never user supplied
    atomic_write_bytes(path, buf.tobytes())
    return path


def cleanup_old(directory: Path, keep_days: int, pattern: str = "*") -> int:
    cutoff, removed = time.time() - keep_days * 86400, 0
    for p in Path(directory).glob(pattern):
        try:
            if p.is_file() and p.name != ".gitkeep" and p.stat().st_mtime < cutoff:
                p.unlink()
                removed += 1
        except OSError:
            pass
    if removed:
        log.info("Retention: removed %d old files from %s", removed, directory)
    return removed
