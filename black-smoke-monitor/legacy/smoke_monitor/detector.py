"""Classical (no AI model) candidate detection: moving, darkening foreground blobs."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

log = logging.getLogger(__name__)

MIN_DARKENING = 15        # pixel must be this much darker than the learned background
MAX_FOREGROUND = 0.5      # more than this much of the frame "moving" = shake / lighting change


@dataclass(frozen=True)
class Detection:
    box: tuple[int, int, int, int]  # x1, y1, x2, y2 in ORIGINAL frame pixels
    score: float                    # blob fill ratio (0-1): a heuristic, not a probability
    label: str


def clip_box(box, width: int, height: int, min_size: int = 8):
    """Clip to the frame; return None if invalid, outside, or too small."""
    x1, y1, x2, y2 = (float(v) for v in box)
    if not all(np.isfinite([x1, y1, x2, y2])):
        return None
    x1, x2 = sorted((x1, x2))
    y1, y2 = sorted((y1, y2))
    x1, y1 = max(0.0, x1), max(0.0, y1)
    x2, y2 = min(float(width), x2), min(float(height), y2)
    if x2 - x1 < min_size or y2 - y1 < min_size:
        return None
    return int(x1), int(y1), int(x2), int(y2)


def scale_box(box, scale_x: float, scale_y: float):
    """Map a box from resized coordinates back to the full frame."""
    x1, y1, x2, y2 = box
    return x1 * scale_x, y1 * scale_y, x2 * scale_x, y2 * scale_y


class MotionSmokeDetector:
    """Learns the static background (MOG2) and reports blobs that are both new/moving AND
    darker than that background. Only proposes candidates: verifier.py and the temporal
    tracker decide, and Claude confirms before any email is sent."""

    def __init__(self, dark_luminance: int = 90, min_blob_fraction: float = 0.002,
                 roi: tuple[tuple[float, float], ...] = (), work_width: int = 640,
                 warmup_frames: int = 20, history: int = 200, max_blobs: int = 3):
        self.dark_luminance = dark_luminance
        self.min_blob_fraction = min_blob_fraction
        self.roi = roi
        self.work_width = work_width
        self.warmup_frames = warmup_frames
        self.max_blobs = max_blobs
        self.bg = cv2.createBackgroundSubtractorMOG2(
            history=history, varThreshold=25, detectShadows=False)
        self.frames_seen = 0
        self._roi_mask: np.ndarray | None = None

    def _roi_for(self, shape) -> np.ndarray | None:
        if not self.roi:
            return None
        if self._roi_mask is None or self._roi_mask.shape != shape:
            h, w = shape
            pts = np.array([[int(x * (w - 1)), int(y * (h - 1))] for x, y in self.roi], np.int32)
            mask = np.zeros(shape, np.uint8)
            cv2.fillPoly(mask, [pts], 255)
            self._roi_mask = mask
        return self._roi_mask

    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        h, w = frame_bgr.shape[:2]
        scale = min(1.0, self.work_width / w)
        small = cv2.resize(frame_bgr, (int(w * scale), int(h * scale))) if scale < 1 else frame_bgr
        sh, sw = small.shape[:2]
        gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)

        fg = self.bg.apply(small)
        self.frames_seen += 1
        if self.frames_seen <= self.warmup_frames:
            return []  # still learning the background
        if (fg > 0).mean() > MAX_FOREGROUND:
            log.debug("Whole scene changed (shake/lighting); no candidates")
            return []

        bg_gray = cv2.cvtColor(self.bg.getBackgroundImage(), cv2.COLOR_BGR2GRAY)
        darker = (bg_gray.astype(np.int16) - gray.astype(np.int16)) >= MIN_DARKENING
        mask = (fg > 0) & (gray < self.dark_luminance) & darker
        roi = self._roi_for((sh, sw))
        if roi is not None:
            mask &= roi > 0
        mask = mask.astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        min_area = self.min_blob_fraction * sh * sw
        blobs = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < min_area:
                continue
            x, y, bw, bh = cv2.boundingRect(c)
            blobs.append((area, (x, y, x + bw, y + bh), area / max(1, bw * bh)))
        blobs.sort(reverse=True)

        out: list[Detection] = []
        for _, box, fill in blobs[:self.max_blobs]:
            clipped = clip_box(scale_box(box, w / sw, h / sh), w, h)
            if clipped:
                out.append(Detection(clipped, float(fill), "dark moving blob"))
        return out


class StubDetector:
    """TEST-ONLY detector returning a fixed box. Never used unless explicitly requested
    (scripts/replay_video.py --stub-detector). The monitor never constructs it."""

    def __init__(self, box=(10, 10, 100, 100), score: float = 0.9, label: str = "stub smoke"):
        self.box, self.score, self.label = box, score, label
        self.enabled = True

    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        if not self.enabled:
            return []
        h, w = frame_bgr.shape[:2]
        b = clip_box(self.box, w, h)
        return [Detection(b, self.score, self.label)] if b else []
