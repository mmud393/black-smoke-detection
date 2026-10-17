"""Frame-difference motion inside a candidate box with global-motion (camera shake) guard.

Motion is SUPPORTING evidence only: slow or stationary smoke exists, and trees/rain also move."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .geometry import Box, clip_box


@dataclass(frozen=True)
class MotionFeatures:
    box_motion: float  # fraction of box pixels that changed
    global_motion: float  # fraction of whole-frame pixels that changed
    camera_shake: bool


def prep_gray(frame_bgr: np.ndarray, size: tuple[int, int] = (320, 180)) -> np.ndarray:
    import cv2

    g = cv2.cvtColor(cv2.resize(frame_bgr, size, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(g, (5, 5), 0)


def compute_motion(prev_gray: np.ndarray, cur_gray: np.ndarray, box: Box, frame_size: tuple[int, int],
                   pixel_thr: int = 12, shake_frac: float = 0.5) -> MotionFeatures:
    diff = np.abs(cur_gray.astype(np.int16) - prev_gray.astype(np.int16)) > pixel_thr
    gh, gw = diff.shape
    sx, sy = gw / frame_size[0], gh / frame_size[1]
    x1, y1, x2, y2 = clip_box((int(box[0] * sx), int(box[1] * sy), int(box[2] * sx), int(box[3] * sy)), gw, gh)
    region = diff[y1:y2, x1:x2]
    glob = float(diff.mean())
    return MotionFeatures(float(region.mean()) if region.size else 0.0, glob, glob >= shake_frac)
