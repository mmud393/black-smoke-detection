"""Dark-smoke appearance checks, motion checks and the temporal episode state machine."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import cv2
import numpy as np

log = logging.getLogger(__name__)

BRIGHT_L = 170           # "light" pixel in a 0-255 luminance scale
WHITE_BRIGHT_FRACTION = 0.5
MIN_CONTRAST = 10.0      # box median must be this much darker than its surround
MAX_GLOBAL_MOTION = 10.0 # mean abs diff outside the box above this => shake/lighting change
MAX_MOTION_FRACTION = 0.9
MOTION_DIFF = 15         # per-pixel gray change that counts as "moving"


@dataclass
class Appearance:
    verdict: str          # dark_smoke | white_smoke | static_dark | uncertain | not_dark
    dark_fraction: float
    bright_fraction: float
    median_l: float
    contrast: float | None
    texture: float
    motion_fraction: float | None
    global_motion: float | None
    reason: str


def _gray(img: np.ndarray) -> np.ndarray:
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def analyze_region(frame: np.ndarray, box, prev_frame: np.ndarray | None,
                   dark_luminance: int = 90, min_dark_fraction: float = 0.40,
                   min_motion_fraction: float = 0.03) -> Appearance:
    """Judge whether a candidate box looks like moving dark smoke.

    Darkness alone is NOT sufficient: a dark machine or shadow is dark but static, so the
    region must also change between independent frames (while the rest of the scene does
    not, which would indicate camera shake or a lighting change)."""
    x1, y1, x2, y2 = box
    gray = _gray(frame)
    region = gray[y1:y2, x1:x2]
    if region.size == 0:
        return Appearance("uncertain", 0, 0, 0, None, 0, None, None, "empty region")
    dark_fraction = float((region < dark_luminance).mean())
    bright_fraction = float((region > BRIGHT_L).mean())
    median_l = float(np.median(region))
    texture = float(region.std())

    # Local contrast against a surrounding ring (inner-region / background separation).
    h, w = gray.shape
    pad = max(8, int(0.25 * max(x2 - x1, y2 - y1)))
    X1, Y1, X2, Y2 = max(0, x1 - pad), max(0, y1 - pad), min(w, x2 + pad), min(h, y2 + pad)
    ring_mask = np.ones((Y2 - Y1, X2 - X1), bool)
    ring_mask[y1 - Y1:y2 - Y1, x1 - X1:x2 - X1] = False
    ring = gray[Y1:Y2, X1:X2][ring_mask]
    contrast = float(np.median(ring) - median_l) if ring.size > 50 else None

    def result(verdict, reason, motion=None, gmotion=None):
        return Appearance(verdict, dark_fraction, bright_fraction, median_l, contrast,
                          texture, motion, gmotion, reason)

    if bright_fraction >= WHITE_BRIGHT_FRACTION and dark_fraction < min_dark_fraction:
        return result("white_smoke", "region is mostly light: steam / white smoke")
    if dark_fraction < min_dark_fraction:
        return result("not_dark", f"dark fraction {dark_fraction:.2f} < {min_dark_fraction}")

    if prev_frame is None or prev_frame.shape[:2] != frame.shape[:2]:
        return result("uncertain", "no previous frame for motion check")
    diff = cv2.absdiff(gray, _gray(prev_frame))
    outside = np.ones(diff.shape, bool)
    outside[y1:y2, x1:x2] = False
    global_motion = float(diff[outside].mean()) if outside.any() else 0.0
    if global_motion > MAX_GLOBAL_MOTION:
        return result("uncertain", "whole scene changed (camera shake / lighting)", None, global_motion)
    motion = float((diff[y1:y2, x1:x2] > MOTION_DIFF).mean())
    if motion < min_motion_fraction:
        return result("static_dark", f"dark but static (motion {motion:.3f}): machine/shadow?",
                      motion, global_motion)
    if motion > MAX_MOTION_FRACTION:
        return result("uncertain", "region changed almost entirely", motion, global_motion)
    if contrast is not None and contrast < -MIN_CONTRAST * 3:
        return result("uncertain", "region far brighter than surroundings", motion, global_motion)
    return result("dark_smoke", "dark, moving, shape-changing region", motion, global_motion)


def iou(a, b) -> float:
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def associated(a, b) -> bool:
    """Same plume region: boxes overlap, or centres are closer than the larger box size."""
    if iou(a, b) > 0.05:
        return True
    ca = ((a[0] + a[2]) / 2, (a[1] + a[3]) / 2)
    cb = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
    size = max(a[2] - a[0], a[3] - a[1], b[2] - b[0], b[3] - b[1])
    return ((ca[0] - cb[0]) ** 2 + (ca[1] - cb[1]) ** 2) ** 0.5 < size


CLEAR, SUSPECTED, ALERTED, CLEARING = "CLEAR", "SUSPECTED", "ALERTED", "CLEARING"


@dataclass
class EpisodeTracker:
    """CLEAR -> SUSPECTED -> ALERTED -> CLEARING -> CLEAR. Only the SUSPECTED->ALERTED
    transition returns True (send exactly one email per continuous episode)."""

    min_detections: int = 3
    min_span: float = 3.0
    clear_seconds: float = 20.0
    max_gap: float = 6.0   # silence that breaks a SUSPECTED chain
    state: str = CLEAR
    _obs: list = field(default_factory=list)   # (time, box)
    last_seen: float = 0.0
    alert_box: tuple | None = None

    def resume_alerted(self, now: float) -> None:
        """After a restart during an active episode: don't re-alert while it persists."""
        self.state, self.last_seen = ALERTED, now

    def update(self, now: float, box) -> bool:
        """box = verified dark-smoke box for this sample, or None. Returns True to alert."""
        if self.state in (ALERTED, CLEARING):
            if box is not None:
                self.state, self.last_seen = ALERTED, now
            else:
                self.state = CLEARING
                if now - self.last_seen >= self.clear_seconds:
                    self.state, self._obs, self.alert_box = CLEAR, [], None
            return False

        # CLEAR / SUSPECTED
        if box is None:
            if self.state == SUSPECTED and self._obs and now - self._obs[-1][0] > self.max_gap:
                self.state, self._obs = CLEAR, []
            return False
        if self._obs and (now - self._obs[-1][0] > self.max_gap or not associated(self._obs[-1][1], box)):
            self._obs = []
        self._obs.append((now, box))
        self.state = SUSPECTED
        if (len(self._obs) >= self.min_detections
                and self._obs[-1][0] - self._obs[0][0] >= self.min_span):
            self.state, self.last_seen, self.alert_box = ALERTED, now, box
            self._obs = []
            return True
        return False
