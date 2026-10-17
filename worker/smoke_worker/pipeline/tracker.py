"""Minimal IoU/center-distance tracker. Times use a monotonic clock for persistence logic."""

from __future__ import annotations

from dataclasses import dataclass, field

from .geometry import Box, box_area, iou


@dataclass
class Observation:
    mono: float  # monotonic seconds (persistence logic)
    wall_iso: str  # wall-clock UTC for records
    box: Box
    model_score: float
    positive: bool  # passed per-frame rules (score, size, ROI, darkness)
    reasons: list[str] = field(default_factory=list)
    darkness: float | None = None
    motion: float | None = None
    changed: bool = False  # box moved / reshaped / internal motion since previous obs


@dataclass
class Track:
    id: int
    obs: list[Observation] = field(default_factory=list)

    @property
    def last(self) -> Observation:
        return self.obs[-1]


def _center_close(a: Box, b: Box) -> bool:
    cx, cy = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2
    dx, dy = (b[0] + b[2]) / 2 - cx, (b[1] + b[3]) / 2 - cy
    diag = max(1.0, ((a[2] - a[0]) ** 2 + (a[3] - a[1]) ** 2) ** 0.5)
    return (dx * dx + dy * dy) ** 0.5 < 0.6 * diag


class Tracker:
    def __init__(self, expire_seconds: float = 6.0, match_iou: float = 0.15, max_obs: int = 200) -> None:
        self.expire, self.match_iou, self.max_obs = expire_seconds, match_iou, max_obs
        self.tracks: list[Track] = []
        self._next = 1

    def update(self, mono: float, detections: list[Observation]) -> list[tuple[Track, Observation]]:
        self.tracks = [t for t in self.tracks if mono - t.last.mono <= self.expire]
        used: set[int] = set()
        out = []
        for d in sorted(detections, key=lambda o: -o.model_score):
            best, best_s = None, 0.0
            for t in self.tracks:
                if t.id in used:
                    continue
                s = iou(t.last.box, d.box)
                if s >= self.match_iou or _center_close(t.last.box, d.box):
                    s = max(s, 0.01)
                    if s > best_s:
                        best, best_s = t, s
            if best is None:
                best = Track(self._next)
                self._next += 1
                self.tracks.append(best)
            else:
                prev = best.last
                area_change = abs(box_area(d.box) - box_area(prev.box)) / max(1, box_area(prev.box))
                d.changed = d.changed or iou(prev.box, d.box) < 0.9 or area_change > 0.08
            used.add(best.id)
            best.obs.append(d)
            del best.obs[: -self.max_obs]
            out.append((best, d))
        return out
