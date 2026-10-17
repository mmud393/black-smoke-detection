"""TEST/DEMO ONLY detector. Reads synthetic 'plume' location from the frame itself (a very dark
blob drawn by fake_camera) so pipeline logic can be exercised deterministically. It is NOT a model
and results from it must never be presented as model output; incidents it creates are is_test=True."""

from __future__ import annotations

import numpy as np

from .types import DetectionCandidate


class FakeDetector:
    model_id = "TEST-ONLY-FAKE-DETECTOR"
    revision = "n/a"
    device = "cpu"
    is_test_double = True

    def warmup(self) -> None:
        pass

    def predict(self, frame_bgr: np.ndarray) -> list[DetectionCandidate]:
        import cv2

        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        mask = (gray < 40).astype(np.uint8)
        n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        out = []
        for i in range(1, n):
            x, y, w, h, area = stats[i]
            if area > 0.002 * gray.size:
                out.append(DetectionCandidate((int(x), int(y), int(x + w), int(y + h)), 0.9, "TEST fake blob", self.model_id))
        return out

    def close(self) -> None:
        pass
