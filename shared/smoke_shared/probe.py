"""Blocking connectivity probe for a camera source. Never returns/prints credentials."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass

from .urls import sanitize_rtsp


@dataclass
class ProbeResult:
    sanitized_url: str
    connected: bool = False
    frame_decoded: bool = False
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    latency_ms: float | None = None
    error: str | None = None

    def dict(self) -> dict:
        return asdict(self)


def open_capture(source: str, transport: str = "tcp", timeout_s: float = 10.0):  # noqa: ANN201
    """cv2.VideoCapture with TCP preferred and connect/read timeouts (FFmpeg backend options)."""
    import os

    import cv2

    if source.lower().startswith(("rtsp://", "rtsps://")):
        ms = int(timeout_s * 1000)
        # Set before open; OpenCV reads this env var when creating the FFmpeg capture.
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            f"rtsp_transport;{'udp' if transport == 'udp' else 'tcp'}|timeout;{ms * 1000}|stimeout;{ms * 1000}"
        )
    cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_s * 1000)
    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_s * 1000)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def probe_source(source: str, transport: str = "tcp", timeout_s: float = 10.0) -> ProbeResult:
    shown = sanitize_rtsp(source) if "://" in source else "<local video file>"
    res = ProbeResult(sanitized_url=shown)
    t0 = time.monotonic()
    cap = None
    try:
        cap = open_capture(source, transport, timeout_s)
        if not cap.isOpened():
            res.error = "CONNECT_FAILED"
            return res
        res.connected = True
        res.fps = float(cap.get(5)) or None
        ok, frame = cap.read()
        res.latency_ms = round((time.monotonic() - t0) * 1000, 1)
        if ok and frame is not None:
            res.frame_decoded = True
            res.height, res.width = frame.shape[:2]
        else:
            res.error = "NO_FRAME"
    except Exception as exc:  # noqa: BLE001
        res.error = type(exc).__name__
    finally:
        if cap is not None:
            cap.release()
    return res
