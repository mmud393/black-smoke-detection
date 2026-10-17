"""SMTP alert sender with a durable JSON outbox and bounded exponential retry."""
from __future__ import annotations

import json
import logging
import smtplib
import ssl
import threading
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from .state import atomic_write_json

log = logging.getLogger(__name__)
BASE_DELAY, MAX_DELAY = 30.0, 900.0


def build_message(cfg, image_path: Path, when_utc: datetime, test: bool = False) -> EmailMessage:
    local = when_utc.astimezone(cfg.timezone)
    msg = EmailMessage()
    msg["From"], msg["To"] = cfg.smtp_from, ", ".join(cfg.alert_to)
    if test:
        msg["Subject"] = "[TEST - NOT A SMOKE ALERT] Black smoke monitor SMTP test"
        msg.set_content("This is a manually requested TEST email. No smoke was detected.")
    else:
        msg["Subject"] = f"[BLACK SMOKE ALERT] {cfg.camera_name} - {local:%Y-%m-%d %H:%M} {local:%Z}"
        msg.set_content(
            f"Possible black smoke detected by camera {cfg.camera_name} at "
            f"{local:%Y-%m-%d %H:%M:%S %Z} ({when_utc:%Y-%m-%d %H:%M:%S} UTC). "
            "See attached screenshot. This is an AI-generated warning and must be checked "
            "according to site safety procedures.")
    if image_path and Path(image_path).exists():
        msg.add_attachment(Path(image_path).read_bytes(), maintype="image",
                           subtype="jpeg", filename=Path(image_path).name)
    return msg


def smtp_send(cfg, msg: EmailMessage) -> None:
    ctx = ssl.create_default_context()  # verifies server certificates
    if cfg.smtp_security == "ssl":
        server = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=cfg.smtp_timeout, context=ctx)
    else:
        server = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=cfg.smtp_timeout)
    with server:
        if cfg.smtp_security == "starttls":
            server.starttls(context=ctx)
        server.login(cfg.smtp_username, cfg.smtp_password)
        server.send_message(msg)


class Outbox:
    """Pending emails are <id>.json; terminal states are renamed .sent / .failed."""

    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    def enqueue(self, event_id: str, image_path: Path, when_utc: datetime) -> Path:
        path = self.dir / f"{event_id}.json"
        atomic_write_json(path, {"event_id": event_id, "image": str(image_path),
                                 "when_utc": when_utc.isoformat(), "attempts": 0,
                                 "next_attempt_epoch": 0})
        return path

    def pending(self) -> list[Path]:
        return sorted(self.dir.glob("*.json"))

    def pending_count(self) -> int:
        return len(self.pending())


class EmailWorker:
    """Background thread: slow SMTP never blocks detection."""

    def __init__(self, cfg, outbox: Outbox, sender=smtp_send, poll_seconds: float = 2.0):
        self.cfg, self.outbox, self.sender, self.poll = cfg, outbox, sender, poll_seconds
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="email-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=cfg_timeout(self.cfg) + 5)

    def notify(self) -> None:
        self._wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            self.process_once()
            self._wake.wait(self.poll)
            self._wake.clear()

    def process_once(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        for path in self.outbox.pending():
            try:
                item = json.loads(path.read_text())
            except ValueError:
                path.rename(path.with_suffix(".failed"))
                log.error("Corrupt outbox item %s marked failed", path.name)
                continue
            if item["next_attempt_epoch"] > now:
                continue
            item["attempts"] += 1
            try:
                when = datetime.fromisoformat(item["when_utc"])
                self.sender(self.cfg, build_message(self.cfg, Path(item["image"]), when))
            except Exception as exc:  # noqa: BLE001
                if item["attempts"] >= self.cfg.email_retry_limit:
                    path.rename(path.with_suffix(".failed"))
                    log.error("Email %s FAILED permanently after %d attempts (%s)",
                              item["event_id"], item["attempts"], type(exc).__name__)
                else:
                    delay = min(BASE_DELAY * 2 ** (item["attempts"] - 1), MAX_DELAY)
                    item["next_attempt_epoch"] = now + delay
                    atomic_write_json(path, item)
                    log.warning("Email %s attempt %d failed (%s); retry in %.0fs",
                                item["event_id"], item["attempts"], type(exc).__name__, delay)
                continue
            path.rename(path.with_suffix(".sent"))
            log.info("Email %s accepted_by_smtp (inbox delivery not confirmed)", item["event_id"])


def cfg_timeout(cfg) -> float:
    return getattr(cfg, "smtp_timeout", 20.0)
