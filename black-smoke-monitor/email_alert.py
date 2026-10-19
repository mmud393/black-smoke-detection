"""Screenshot saving and SMTP alert delivery on a single bounded background worker."""
from __future__ import annotations

import logging
import queue
import smtplib
import ssl
import threading
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

import cv2
import numpy as np

from config import Settings

log = logging.getLogger("email")


def save_screenshot(s: Settings, frame: np.ndarray, box: tuple, when: datetime) -> Path:
    """Write one annotated JPEG (annotation is on a copy; the frame is untouched)."""
    s.screenshot_dir.mkdir(parents=True, exist_ok=True)
    img = frame.copy()
    x1, y1, x2, y2 = box
    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 3)
    path = s.screenshot_dir / f"black_smoke_{when.strftime('%Y%m%dT%H%M%S_%f%z')}.jpg"
    if not cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, s.screenshot_jpeg_quality]):
        raise OSError("could not write screenshot")
    return path


def build_message(s: Settings, path: Path, when: datetime, confidence: float, dark_ratio: float) -> EmailMessage:
    stamp = when.strftime("%Y-%m-%d %H:%M:%S %Z")
    msg = EmailMessage()
    msg["Subject"] = f"{s.email_subject_prefix} - {s.camera_name} - {stamp}"
    msg["From"] = s.smtp_from
    msg["To"] = ", ".join(s.smtp_to)
    msg.set_content(
        f"Black smoke may have been detected by {s.camera_name} at {stamp}. "
        f"Please review the attached screenshot.\n\n"
        f"Estimates only: model confidence {confidence:.2f}, dark-pixel ratio {dark_ratio:.2f}.\n"
        f"This is supplementary monitoring, not a certified fire alarm."
    )
    msg.add_attachment(path.read_bytes(), maintype="image", subtype="jpeg", filename=path.name)
    return msg


def send_via_smtp(s: Settings, msg: EmailMessage) -> None:
    """STARTTLS with a verifying context; never falls back to plaintext authentication."""
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(s.smtp_username, s.smtp_password)
        smtp.send_message(msg)


class EmailWorker:
    """One daemon thread; submit() never blocks the camera/inference loop."""

    def __init__(self, s: Settings, sender=send_via_smtp, retry_delay: float = 5.0):
        self._s, self._send, self._delay = s, sender, retry_delay
        self._q: queue.Queue = queue.Queue(maxsize=4)
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, name="email", daemon=True)
        self._t.start()

    def submit(self, msg: EmailMessage) -> bool:
        try:
            self._q.put_nowait(msg)
            return True
        except queue.Full:
            log.error("Email queue full; alert dropped")
            return False

    def close(self, timeout: float = 5) -> None:
        self._stop.set()
        self._t.join(timeout)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                msg = self._q.get(timeout=0.2)
            except queue.Empty:
                continue
            for attempt in range(self._s.smtp_retries + 1):
                try:
                    self._send(self._s, msg)
                    log.info("Alert email handed to SMTP server")
                    break
                except Exception as exc:  # message omitted: SMTP errors may echo credentials
                    log.warning("SMTP attempt %d failed (%s)", attempt + 1, type(exc).__name__)
                    if attempt < self._s.smtp_retries and self._stop.wait(self._delay):
                        return
            else:
                log.error("Alert email failed after %d attempts", self._s.smtp_retries + 1)


def now_in_tz(s: Settings) -> datetime:
    return datetime.now(ZoneInfo(s.app_timezone))
