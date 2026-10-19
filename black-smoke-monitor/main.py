"""Watch RTSP camera -> detect black smoke -> save screenshot -> email alert."""
from __future__ import annotations

import logging
import signal
import sys
import threading
import time

import cv2

from camera import CameraReader
from config import ConfigError, ensure_env_file, load_settings
from detector import BlackSmokeVerifier, EventTracker, SmokeModel, ensure_model
from email_alert import EmailWorker, build_message, now_in_tz, save_screenshot

log = logging.getLogger("main")


def run(s, camera, model, stop: threading.Event, worker=None) -> None:
    verifier, tracker = BlackSmokeVerifier(s), EventTracker(s)
    interval, last_seq, was_up = 1.0 / s.process_fps, 0, True
    while not stop.is_set():
        started = time.monotonic()
        pkt = camera.latest()
        if pkt is None:
            if was_up:
                tracker.camera_lost()
                was_up = False
        elif pkt.seq != last_seq:
            was_up, last_seq = True, pkt.seq
            frame, scale = pkt.frame, 1.0
            if frame.shape[1] > s.frame_max_width:
                scale = s.frame_max_width / frame.shape[1]
                frame = cv2.resize(frame, (s.frame_max_width, int(frame.shape[0] * scale)))
            try:
                verdict = verifier.evaluate(frame, model.detect(frame), pkt.connection_id)
            except Exception as exc:  # inference failure must never alert or stop monitoring
                log.error("Inference failure: %s: %s", type(exc).__name__, exc)
                stop.wait(interval)
                continue
            if tracker.observe(verdict.positive, time.monotonic()):
                try:
                    handle_event(s, pkt.frame, verdict, worker, scale)
                except Exception as exc:
                    log.error("Alert handling failed: %s", type(exc).__name__)
        stop.wait(max(0.0, interval - (time.monotonic() - started)))


def handle_event(s, frame, verdict, worker, scale: float = 1.0) -> None:
    """`frame` is the original camera frame; the box is in processed coordinates, so scale it back."""
    when = now_in_tz(s)
    box = tuple(int(v / scale) for v in verdict.candidate.box)
    path = save_screenshot(s, frame, box, when)
    if not s.email_enabled or worker is None:
        log.warning("Black smoke confirmed; screenshot %s (email disabled)", path)
        return
    log.warning("Black smoke confirmed; screenshot %s; queueing email", path)
    worker.submit(build_message(s, path, when, verdict.candidate.confidence, verdict.dark_ratio))


def main() -> int:
    missing = ensure_env_file()
    try:
        s = load_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    logging.basicConfig(level=s.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if missing:
        log.warning(".env is missing keys: %s", ", ".join(missing))
    if s.rtsp_placeholders():
        print("Edit .env first: RTSP_URL still holds the template placeholder.", file=sys.stderr)
        return 2
    try:
        ensure_model(s)
        model = SmokeModel(s)
    except Exception as exc:
        print(f"Model setup failed: {exc}", file=sys.stderr)
        return 3
    log.info("Starting: camera=%r email_enabled=%s", s.camera_name, s.email_enabled)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    camera = CameraReader(s)
    worker = EmailWorker(s) if s.email_enabled else None
    camera.start()
    try:
        run(s, camera, model, stop, worker)
    finally:
        camera.stop()
        if worker:
            worker.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
