"""Dahua RTSP reader (or video file) with reconnect and a bounded latest-frame buffer."""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class Frame:
    image: np.ndarray
    captured_at: float  # time.monotonic()
    seq: int


class LatestFrameBuffer:
    """Holds only the newest frame; older ones are dropped (no backlog)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: Frame | None = None

    def put(self, frame: Frame) -> None:
        with self._lock:
            self._frame = frame

    def get(self) -> Frame | None:
        with self._lock:
            return self._frame

    def clear(self) -> None:
        with self._lock:
            self._frame = None


def open_capture(source: str, transport: str = "tcp", timeout_s: float = 10.0):
    """Open an OpenCV/FFmpeg capture. RTSP defaults to TCP with socket timeouts."""
    import cv2

    if source.lower().startswith("rtsp"):
        us = int(timeout_s * 1_000_000)
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            f"rtsp_transport;{transport}|stimeout;{us}|timeout;{us}"
        )
    return cv2.VideoCapture(source, cv2.CAP_FFMPEG)


class CameraReader:
    """Capture thread: reads continuously, reconnects with exponential backoff."""

    def __init__(self, source: str, display_name: str, transport: str = "tcp",
                 connect_timeout: float = 10.0, stall_timeout: float = 10.0,
                 capture_factory: Callable | None = None, loop_file: bool = False,
                 max_backoff: float = 30.0, sleep: Callable[[float], None] | None = None):
        self.source = source
        self.display_name = display_name  # redacted; safe for logs
        self.transport = transport
        self.connect_timeout = connect_timeout
        self.stall_timeout = stall_timeout
        self._factory = capture_factory or (lambda: open_capture(source, transport, connect_timeout))
        self.loop_file = loop_file
        self.max_backoff = max_backoff
        self.buffer = LatestFrameBuffer()
        self.status = "starting"  # starting | connected | unavailable | stopped
        self.reconnects = 0
        self._stop = threading.Event()
        self._sleep = sleep or (lambda s: self._stop.wait(s))
        self._thread: threading.Thread | None = None
        self._seq = 0

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="camera-capture", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=15)
        self.status = "stopped"

    def frame_age(self) -> float | None:
        f = self.buffer.get()
        return None if f is None else time.monotonic() - f.captured_at

    def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            cap = None
            try:
                cap = self._factory()
                if cap is None or not cap.isOpened():
                    raise ConnectionError("could not open stream")
                log.info("Camera connected: %s", self.display_name)
                self.status = "connected"
                backoff = 1.0
                self._read_loop(cap)
            except Exception as exc:  # keep retrying forever
                log.warning("Camera error (%s): %s", self.display_name, type(exc).__name__)
            finally:
                self.status = "unavailable"
                self.buffer.clear()  # never serve stale frames across a reconnect
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:  # noqa: BLE001
                        pass
            if self._stop.is_set():
                break
            self.reconnects += 1
            log.warning("Camera unavailable; reconnecting in %.0fs", backoff)
            self._sleep(backoff)
            backoff = min(backoff * 2, self.max_backoff)

    def _read_loop(self, cap) -> None:
        last_ok = time.monotonic()
        while not self._stop.is_set():
            ok, img = cap.read()
            now = time.monotonic()
            if ok and img is not None:
                last_ok = now
                self._seq += 1
                self.buffer.put(Frame(img, now, self._seq))
                continue
            if self.loop_file:
                import cv2
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            if now - last_ok > self.stall_timeout:
                raise TimeoutError("stream stalled")
            time.sleep(0.05)
