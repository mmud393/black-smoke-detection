"""Per-frame candidate screening against the detection profile. Every rejection has a reason code."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..inference.types import DetectionCandidate
from .darkness import DarknessFeatures, compute_darkness
from .geometry import box_area, clip_box, overlap_fraction


@dataclass
class ProfileParams:
    candidate_score_min: float = 0.30  # arbitrary starting value; needs evaluation on local footage
    darkness_l_max: float = 45.0  # median L* upper bound for "dark"
    darkness_contrast_min: float = 12.0  # L* units darker than local background
    sat_max: float = 0.55  # near-neutral colour
    min_box_area_frac: float = 0.002
    max_box_area_frac: float = 0.60
    ignore_overlap_max: float = 0.5
    roi_overlap_min: float = 0.3


@dataclass
class Screened:
    cand: DetectionCandidate
    positive: bool
    reasons: list[str]
    darkness: DarknessFeatures | None


def screen(frame_bgr: np.ndarray, cands: list[DetectionCandidate], p: ProfileParams,
           roi_mask: np.ndarray | None, ignore_mask: np.ndarray | None) -> list[Screened]:
    h, w = frame_bgr.shape[:2]
    out: list[Screened] = []
    for c in cands:
        box = clip_box(c.box_xyxy, w, h)
        reasons: list[str] = []
        if c.score < p.candidate_score_min:
            reasons.append("SCORE_BELOW_MIN")
        frac = box_area(box) / float(w * h)
        if frac < p.min_box_area_frac:
            reasons.append("BOX_TOO_SMALL")
        if frac > p.max_box_area_frac:
            reasons.append("BOX_TOO_LARGE")
        if roi_mask is not None and overlap_fraction(box, roi_mask) < p.roi_overlap_min:
            reasons.append("OUTSIDE_ROI")
        if ignore_mask is not None and overlap_fraction(box, ignore_mask) > p.ignore_overlap_max:
            reasons.append("IN_IGNORE_ZONE")
        dark = None
        if not reasons:
            dark = compute_darkness(frame_bgr, box)
            if dark is None:
                reasons.append("REGION_UNUSABLE")
            else:
                if dark.evidence_quality == "inner_box":
                    reasons.append("EVIDENCE_QUALITY_REDUCED_NO_MASK")
                if dark.median_l > p.darkness_l_max:
                    reasons.append("NOT_DARK")
                elif dark.contrast is not None and dark.contrast < p.darkness_contrast_min:
                    reasons.append("DARK_LOW_CONTRAST")  # e.g. night scene: ambiguous
                else:
                    reasons.append("DARK_OK")
                if dark.mean_sat > p.sat_max:
                    reasons.append("COLORED_NOT_NEUTRAL")
        blocking = {"SCORE_BELOW_MIN", "BOX_TOO_SMALL", "BOX_TOO_LARGE", "OUTSIDE_ROI", "IN_IGNORE_ZONE", "REGION_UNUSABLE",
                    "NOT_DARK", "DARK_LOW_CONTRAST", "COLORED_NOT_NEUTRAL"}
        if not (set(reasons) & blocking):
            reasons.append("MODEL_SCORE_OK")
        out.append(Screened(c, not (set(reasons) & blocking), reasons, dark))
    return out
