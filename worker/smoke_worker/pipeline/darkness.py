"""Darkness / appearance features for a candidate region.

Heuristics (NOT validated on real footage; thresholds live in the detection profile):
- Brightness is measured as CIELAB L* (0..100) which tracks perceived lightness better than HSV V.
- We take the MEDIAN over the region (robust to specks/edges), after shrinking the box (conservative
  inner region) when no segmentation mask is available, and we say so (evidence_quality).
- Local contrast = median L* of a ring around the box minus the region median. Black smoke in daylight
  is darker than its surroundings; at night the surroundings are dark too, so contrast is small and the
  decision becomes UNCERTAIN instead of VERIFIED.
- Saturation is reported because black smoke is near-neutral (low S); coloured dark objects are not.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .geometry import Box, clip_box


@dataclass(frozen=True)
class DarknessFeatures:
    median_l: float  # L* 0..100
    p25_l: float
    p75_l: float
    mean_sat: float  # 0..1
    background_l: float | None
    contrast: float | None  # background_l - median_l (positive = darker than surroundings)
    darkness_score: float  # 1 - median_l/100, a heuristic 0..1 value (not a probability)
    evidence_quality: str  # "mask" | "inner_box"
    pixels: int


def _to_lab_hsv(bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    import cv2

    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return lab[..., 0].astype(np.float32) * (100.0 / 255.0), hsv[..., 1].astype(np.float32) / 255.0


def compute_darkness(frame_bgr: np.ndarray, box: Box, mask: np.ndarray | None = None, inner_shrink: float = 0.15,
                     ring_expand: float = 0.5) -> DarknessFeatures | None:
    h, w = frame_bgr.shape[:2]
    x1, y1, x2, y2 = clip_box(box, w, h)
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    L, S = _to_lab_hsv(frame_bgr)
    if mask is not None:
        sel = mask[y1:y2, x1:x2] > 0
        quality = "mask"
    else:
        dx, dy = int((x2 - x1) * inner_shrink), int((y2 - y1) * inner_shrink)
        sel = np.zeros((y2 - y1, x2 - x1), bool)
        sel[dy : (y2 - y1) - dy, dx : (x2 - x1) - dx] = True
        quality = "inner_box"
    if sel.sum() < 16:
        return None
    Lr, Sr = L[y1:y2, x1:x2][sel], S[y1:y2, x1:x2][sel]
    med = float(np.median(Lr))

    # background ring: expanded box minus the box itself
    ex, ey = int((x2 - x1) * ring_expand), int((y2 - y1) * ring_expand)
    X1, Y1, X2, Y2 = clip_box((x1 - ex, y1 - ey, x2 + ex, y2 + ey), w, h)
    ring = np.ones((Y2 - Y1, X2 - X1), bool)
    ring[y1 - Y1 : y2 - Y1, x1 - X1 : x2 - X1] = False
    bg = float(np.median(L[Y1:Y2, X1:X2][ring])) if ring.sum() >= 16 else None
    return DarknessFeatures(
        median_l=med, p25_l=float(np.percentile(Lr, 25)), p75_l=float(np.percentile(Lr, 75)),
        mean_sat=float(Sr.mean()), background_l=bg, contrast=(bg - med) if bg is not None else None,
        darkness_score=round(1.0 - med / 100.0, 4), evidence_quality=quality, pixels=int(sel.sum()),
    )
