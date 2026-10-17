"""Temporal verifier: require N positive observations over >= T seconds on one track.

Uses distinct, monotonic timestamps (not adjacent frames from one instant), tolerates dropped frames
(max_gap) and applies hysteresis: a track stays verified until positives stop for `max_gap` seconds."""

from __future__ import annotations

from dataclasses import dataclass

from smoke_shared.enums import Decision

from .tracker import Observation, Track


@dataclass(frozen=True)
class TemporalParams:
    min_count: int = 3
    min_seconds: float = 3.0
    max_gap_seconds: float = 4.0  # tolerated gap between positives (dropped frames)
    min_separation_seconds: float = 0.3  # observations closer than this count once
    require_change: bool = True  # static dark objects (parked vehicle) must not verify
    min_changed_obs: int = 1
    ambiguous_ok: bool = False


@dataclass(frozen=True)
class Verdict:
    decision: Decision
    reasons: list[str]
    positives: int
    span_seconds: float


def evaluate(track: Track, now_mono: float, p: TemporalParams) -> Verdict:
    reasons: list[str] = list(track.last.reasons)
    # distinct positives, newest chain without a gap larger than max_gap
    positives: list[Observation] = []
    for o in reversed(track.obs):
        if not o.positive:
            continue
        if positives and positives[-1].mono - o.mono > p.max_gap_seconds:
            break
        if positives and positives[-1].mono - o.mono < p.min_separation_seconds:
            continue
        positives.append(o)
    positives.reverse()
    n = len(positives)
    span = (positives[-1].mono - positives[0].mono) if n else 0.0
    if not n or now_mono - positives[-1].mono > p.max_gap_seconds:
        return Verdict(Decision.CANDIDATE if track.obs else Decision.NONE, reasons + ["NO_RECENT_POSITIVE"], n, span)
    if n < p.min_count or span < p.min_seconds:
        return Verdict(Decision.CANDIDATE, reasons + [f"INSUFFICIENT_OBSERVATIONS:{n}/{p.min_count} over {span:.1f}s"], n, span)
    if p.require_change and sum(o.changed or (o.motion or 0) > 0.02 for o in positives) < p.min_changed_obs:
        return Verdict(Decision.UNCERTAIN, reasons + ["STATIC_NO_CHANGE"], n, span)
    return Verdict(Decision.VERIFIED_BY_RULES, reasons + [f"PERSISTENT:{n}_obs_over_{span:.1f}s"], n, span)
