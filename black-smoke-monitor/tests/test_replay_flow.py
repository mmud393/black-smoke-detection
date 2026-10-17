"""End-to-end flow with the TEST-ONLY stub detector on synthetic frames (no camera/SMTP)."""
import json

import numpy as np

from smoke_monitor.detector import StubDetector
from smoke_monitor.monitor import Monitor


class NoEmail:
    def __init__(self):
        self.notified = 0

    def notify(self):
        self.notified += 1

    def start(self): ...
    def stop(self): ...


def frames(n):
    """Dark box whose left edge alternates so it 'moves' between sampled frames."""
    for i in range(n):
        img = np.full((240, 320, 3), 170, np.uint8)
        img[60:180, 80:240] = 40
        if i % 2:
            img[60:180, 80:120] = 130
        yield img


def make(cfg):
    det = StubDetector(box=(80, 60, 240, 180))
    return Monitor(cfg, det, reader=object(), email_worker=NoEmail()), det


def test_one_alert_per_episode_and_screenshot(cfg):
    mon, det = make(cfg)
    shots = [s for i, img in enumerate(frames(40)) if (s := mon.process_frame(img, float(i)))]
    assert len(shots) == 1
    assert len(list(mon.shots_dir.glob("black_smoke_*.jpg"))) == 1
    assert mon.outbox.pending_count() == 1 and mon.emailer.notified == 1
    # smoke disappears, episode clears, returns -> second alert
    det.enabled = False
    clear = np.full((240, 320, 3), 170, np.uint8)
    for i in range(40, 70):
        mon.process_frame(clear, float(i))
    assert json.loads(mon.state.path.read_text())["active"] is False
    det.enabled = True
    again = [s for i, img in enumerate(frames(10)) if (s := mon.process_frame(img, 100.0 + i))]
    assert len(again) == 1 and mon.outbox.pending_count() == 2


def test_no_screenshot_for_ordinary_or_static_frames(cfg):
    mon, det = make(cfg)
    quiet = np.full((240, 320, 3), 170, np.uint8)
    static = quiet.copy()
    static[60:180, 80:240] = 40
    for i in range(20):
        mon.process_frame(quiet, float(i))
    for i in range(20, 40):
        mon.process_frame(static, float(i))  # dark but never moves
    assert not list(mon.shots_dir.glob("*.jpg")) and mon.outbox.pending_count() == 0


def test_restart_during_active_episode_does_not_realert(cfg):
    mon, _ = make(cfg)
    for i, img in enumerate(frames(10)):
        mon.process_frame(img, float(i))
    mon2, _ = make(cfg)  # same data dir: state says active
    assert mon2.tracker.state == "ALERTED"
    assert not any(mon2.process_frame(img, float(i)) for i, img in enumerate(frames(10)))
