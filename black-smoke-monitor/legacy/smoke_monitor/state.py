"""Minimal incident state persisted atomically so a restart does not re-alert a live plume."""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path

log = logging.getLogger(__name__)
RESUME_WINDOW_SECONDS = 600  # a restart within 10 min of an active alert resumes as ALERTED


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def atomic_write_json(path: Path, obj) -> None:
    atomic_write_bytes(path, json.dumps(obj, indent=2).encode())


class AlertState:
    def __init__(self, state_dir: Path):
        self.path = Path(state_dir) / "last_alert.json"

    def load(self) -> dict | None:
        try:
            return json.loads(self.path.read_text())
        except (FileNotFoundError, ValueError):
            return None

    def save(self, event_id: str, active: bool) -> None:
        atomic_write_json(self.path, {"event_id": event_id, "active": active,
                                      "updated_epoch": time.time()})

    def should_resume(self) -> bool:
        s = self.load()
        return bool(s and s.get("active") and time.time() - s.get("updated_epoch", 0) < RESUME_WINDOW_SECONDS)
