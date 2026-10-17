from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class DetectionCandidate:
    box_xyxy: tuple[int, int, int, int]  # ORIGINAL frame pixel coordinates
    score: float  # model similarity/box score. NOT a calibrated probability.
    text_label: str
    model_id: str


class SmokeDetector(Protocol):
    """Actual signature matches the master spec; `predict` is synchronous and called only by the
    shared inference scheduler (never from API handlers). `info` reports model state for health."""

    model_id: str
    revision: str
    device: str
    is_test_double: bool

    def warmup(self) -> None: ...
    def predict(self, frame_bgr: np.ndarray) -> list[DetectionCandidate]: ...
    def close(self) -> None: ...
