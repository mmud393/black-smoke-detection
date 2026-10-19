"""RTSP capture thread with a single latest-frame buffer and automatic reconnect."""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np

from config import Settings, redact_url

log = logging.getLogger("camera")


@dataclass(frozen=True)
class FramePacket:
    frame: np.ndarray
    seq: int            # increases with every frame read
    connection_id: int  # changes after each (re)connect, so consumers reset motion references
    captured_at: float  # time.monotonic()


class CameraReader:
    def __init__(self, settings: Settings, capture_factory=None):
        self._s = settings
        self._factory = capture_factory or self._open_capture
        self._lock = threading.Lock()
        self._latest: FramePacket | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="camera", daemon=True)
        self._seq = 0
        self._conn = 0
        self.connected = False

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def latest(self) -> FramePacket | None:
        """Newest frame, or None when none has arrived within CAMERA_NO_FRAME_TIMEOUT_SECONDS."""
        with self._lock:
            p = self._latest
        if p is None or time.monotonic() - p.captured_at > self._s.camera_no_frame_timeout_seconds:
            return None
        return p

    def _open_capture(self):
        # OpenCV reads FFmpeg options from this env var; timeouts are in microseconds.
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            f"rtsp_transport;{self._s.rtsp_transport}|stimeout;{self._s.camera_open_timeout_ms * 1000}"
        )
        cap = cv2.VideoCapture(self._s.rtsp_url, cv2.CAP_FFMPEG)
        for prop, val in ((cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self._s.camera_open_timeout_ms),
                          (cv2.CAP_PROP_READ_TIMEOUT_MSEC, self._s.camera_read_timeout_ms),
                          (cv2.CAP_PROP_BUFFERSIZE, 1)):
            cap.set(prop, val)
        return cap

    def _run(self) -> None:
        while not self._stop.is_set():
            cap = None
            try:
                cap = self._factory()
                if not cap.isOpened():
                    raise ConnectionError("could not open stream")
                self._conn += 1
                self.connected = True
                log.info("Camera %s connected", self._s.camera_name)
                while not self._stop.is_set():
                    ok, frame = cap.read()
                    if not ok or frame is None or frame.size == 0:
                        raise ConnectionError("read failed or invalid frame")
                    self._seq += 1
                    pkt = FramePacket(frame, self._seq, self._conn, time.monotonic())
                    with self._lock:
                        self._latest = pkt
            except Exception as exc:  # reconnect on anything; never stop monitoring
                log.warning("Camera %s disconnected: %s", self._s.camera_name, redact_url(str(exc)))
            finally:
                self.connected = False
                if cap is not None:
                    cap.release()
            self._stop.wait(self._s.camera_reconnect_seconds)
