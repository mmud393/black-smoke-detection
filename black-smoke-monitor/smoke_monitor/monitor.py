"""Orchestrates capture -> detect -> verify -> screenshot -> email, 24/7."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

import cv2

from .camera import CameraReader
from .email_alert import EmailWorker, Outbox
from .screenshot import cleanup_old, save_screenshot
from .state import AlertState
from .verifier import EpisodeTracker, analyze_region

log = logging.getLogger(__name__)
HEALTH_EVERY = 60.0
RETENTION_EVERY = 3600.0


class Monitor:
    def __init__(self, cfg, detector, reader: CameraReader | None = None,
                 email_worker: EmailWorker | None = None):
        self.cfg, self.detector = cfg, detector
        data = cfg.data_dir
        self.shots_dir = data / "screenshots"
        self.state = AlertState(data / "state")
        self.outbox = Outbox(data / "email_outbox")
        self.reader = reader or CameraReader(
            cfg.rtsp_url, cfg.redacted_url, cfg.rtsp_transport, cfg.connect_timeout, cfg.stall_timeout)
        self.emailer = email_worker or EmailWorker(cfg, self.outbox)
        self.tracker = EpisodeTracker(cfg.min_detections, cfg.min_span_seconds,
                                      cfg.clear_seconds)
        if self.state.should_resume():
            self.tracker.resume_alerted(time.monotonic())
            log.info("Resuming active episode from previous run; no duplicate alert while it persists")
        self.stop_event = threading.Event()
        self._prev_gray = None
        self._last_seq = -1
        self.last_inference_s = 0.0
        self.last_inference_at: float | None = None
        self.degraded = False

    # one sampling step, separated for testing / replay
    def process_frame(self, image, now: float) -> str | None:
        """Returns screenshot path string when a NEW verified episode alert was queued."""
        best = None
        t0 = time.monotonic()
        dets = self.detector.detect(image)
        self.last_inference_s = time.monotonic() - t0
        self.last_inference_at = time.monotonic()
        for d in dets:
            ap = analyze_region(image, d.box, self._prev_gray, self.cfg.dark_luminance,
                                self.cfg.min_dark_fraction, self.cfg.min_motion_fraction)
            log.debug("candidate %s score=%.2f -> %s (%s)", d.box, d.score, ap.verdict, ap.reason)
            if ap.verdict == "dark_smoke" and (best is None or d.score > best.score):
                best = d
        self._prev_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if not self.tracker.update(now, best.box if best else None):
            if self.tracker.state == "CLEAR" and (s := self.state.load()) and s.get("active"):
                self.state.save(s["event_id"], False)
            return None
        return self._raise_alert(image, best.box)

    def _raise_alert(self, image, box) -> str:
        when = datetime.now(timezone.utc)
        path = save_screenshot(image, box, self.shots_dir, self.cfg.timezone, self.cfg.camera_name, when)
        event_id = path.stem.removeprefix("black_smoke_")
        self.outbox.enqueue(event_id, path, when)
        self.state.save(event_id, True)
        self.emailer.notify()
        log.warning("BLACK SMOKE episode verified: %s (email queued)", path.name)
        return str(path)

    def run(self) -> None:
        interval = 1.0 / self.cfg.inference_fps
        self.reader.start()
        self.emailer.start()
        last_health = last_retention = 0.0
        next_run = time.monotonic()
        log.info("Monitoring started (camera=%s, inference_fps=%s)", self.cfg.redacted_url, self.cfg.inference_fps)
        try:
            while not self.stop_event.is_set():
                now = time.monotonic()
                frame = self.reader.buffer.get()
                if frame is not None and frame.seq != self._last_seq:
                    age = now - frame.captured_at
                    if age > self.cfg.max_frame_age:
                        log.warning("Skipping stale frame (age %.1fs)", age)
                    else:
                        self._last_seq = frame.seq
                        try:
                            self.process_frame(frame.image, now)
                            self.degraded = False
                        except Exception:  # noqa: BLE001
                            self.degraded = True
                            log.exception("Inference error (degraded)")
                            self.stop_event.wait(2.0)
                        if time.monotonic() - now > interval * 1.5:
                            log.warning("Degraded: inference took %.2fs > interval %.2fs; "
                                        "lower INFERENCE_FPS or use faster hardware",
                                        time.monotonic() - now, interval)
                if now - last_health >= HEALTH_EVERY:
                    last_health = now
                    fa = self.reader.frame_age()
                    log.info("health camera=%s frame_age=%s inference_s=%.2f state=%s pending_emails=%d%s",
                             self.reader.status, "n/a" if fa is None else f"{fa:.1f}s",
                             self.last_inference_s, self.tracker.state, self.outbox.pending_count(),
                             " DEGRADED" if self.degraded else "")
                if now - last_retention >= RETENTION_EVERY:
                    last_retention = now
                    cleanup_old(self.shots_dir, self.cfg.keep_days, "*.jpg")
                    cleanup_old(self.outbox.dir, self.cfg.keep_days, "*.sent")
                    cleanup_old(self.outbox.dir, self.cfg.keep_days, "*.failed")
                next_run += interval
                self.stop_event.wait(max(0.0, next_run - time.monotonic()))
                if next_run < time.monotonic() - interval:
                    next_run = time.monotonic()  # drop backlog instead of catching up
        finally:
            log.info("Shutting down")
            self.reader.stop()
            self.emailer.stop()
            self.state.path.parent.mkdir(parents=True, exist_ok=True)

    def stop(self) -> None:
        self.stop_event.set()
