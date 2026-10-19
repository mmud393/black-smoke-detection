import numpy as np
import pytest

from camera import CameraReader
from detector import BlackSmokeVerifier, Candidate, EventTracker, ModelError, SmokeModel, clip_box

BOX = (20, 20, 120, 120)
CAND = [Candidate(BOX, 0.9)]


def frame(level):
    return np.full((200, 200, 3), level, np.uint8)


def moving(level_a, level_b):
    """Two frames whose box region differs strongly (all pixels move)."""
    return frame(level_a), frame(level_b)


def run_pair(v, a, b, cand=CAND, conn=1):
    v.evaluate(a, cand, conn)
    return v.evaluate(b, cand, conn)


def test_dark_moving_smoke_is_positive(settings):
    assert run_pair(BlackSmokeVerifier(settings), *moving(80, 40)).positive


def test_white_smoke_rejected_despite_confidence(settings):
    assert not run_pair(BlackSmokeVerifier(settings), *moving(200, 240)).positive


def test_dark_frame_without_smoke_class_rejected(settings):
    assert not run_pair(BlackSmokeVerifier(settings), *moving(30, 10), cand=[]).positive


def test_dark_static_region_rejected(settings):
    assert not run_pair(BlackSmokeVerifier(settings), frame(30), frame(30)).positive


def test_first_frame_and_reconnect_are_not_motion(settings):
    v = BlackSmokeVerifier(settings)
    assert not v.evaluate(frame(80), CAND, 1).positive
    assert not v.evaluate(frame(30), CAND, 2).positive  # new connection -> reference only


def test_tiny_region_rejected(mk):
    v = BlackSmokeVerifier(mk(SMOKE_REGION_MIN_AREA_PX=100000))
    assert not run_pair(v, *moving(80, 40)).positive


def test_box_validation():
    assert clip_box(0, 0, 10, 10, 100, 100) == (0, 0, 10, 10)
    assert clip_box(-5, -5, 500, 500, 100, 100) == (0, 0, 100, 100)
    assert clip_box(float("nan"), 0, 10, 10, 100, 100) is None
    assert clip_box(50, 50, 50, 60, 100, 100) is None
    assert clip_box(200, 200, 300, 300, 100, 100) is None


class FakeSession:
    """YOLO-style output (1, 5, anchors): cx, cy, w, h in 1024-px input coordinates + class score."""

    def __init__(self, anchors):
        self.out = np.array(anchors, np.float32).T[None]

    def get_inputs(self):
        return [type("I", (), {"name": "images"})()]

    def run(self, _, feed):
        assert feed["images"].shape == (1, 3, 1024, 1024)
        return [self.out]


def test_model_threshold_scaling_and_nms(settings):
    anchors = [
        [512, 512, 400, 400, 0.9],   # kept
        [514, 514, 400, 400, 0.8],   # duplicate -> removed by NMS
        [100, 100, 50, 50, 0.1],     # below MODEL_CONFIDENCE_MIN
    ]
    got = SmokeModel(settings, FakeSession(anchors)).detect(frame(100))  # 200x200 frame
    assert len(got) == 1 and got[0].box == (60, 60, 139, 139) and got[0].confidence > 0.89


def test_model_invalid_box_dropped_and_bad_shape_refused(settings):
    assert SmokeModel(settings, FakeSession([[float("nan")] * 4 + [0.9]])).detect(frame(100)) == []
    bad = FakeSession([[1, 2, 3, 4, 5]])
    bad.out = np.zeros((1, 3, 10), np.float32)
    with pytest.raises(ModelError):
        SmokeModel(settings, bad).detect(frame(100))


def test_model_class_name_checked_against_metadata(mk):
    class Meta(FakeSession):
        def get_modelmeta(self):
            return type("M", (), {"custom_metadata_map": {"names": "{0: 'flame'}"}})()

    with pytest.raises(ModelError, match="not in model classes"):
        SmokeModel(mk(), Meta([[1, 1, 1, 1, 1]]))


def test_one_positive_does_not_trigger_and_window_does(settings):
    t = EventTracker(settings)  # 3 of 5
    assert [t.observe(p, i) for i, p in enumerate([True, False, True, False, True])][-1] is True


def test_one_alert_per_episode_then_rearm_after_clear_and_cooldown(mk):
    t = EventTracker(mk(EMAIL_COOLDOWN_SECONDS=100, EVENT_CLEAR_SECONDS=20))
    alerts = [t.observe(True, i) for i in range(30)]
    assert alerts.count(True) == 1 and t.active
    for i in range(30, 60):
        t.observe(False, i)  # >20s without smoke -> cleared
    assert not t.active
    assert not any(t.observe(True, 60 + i) for i in range(5))  # confirmed again, but inside cooldown
    for i in range(65, 90):
        t.observe(False, i)
    assert any(t.observe(True, 200 + i) for i in range(5))  # past cooldown -> new alert


def test_camera_outage_does_not_count_as_cleared(mk):
    t = EventTracker(mk(EVENT_CLEAR_SECONDS=20))
    for i in range(3):
        t.observe(True, i)
    t.camera_lost()
    t.observe(False, 500)  # camera back after a long gap
    assert t.active


def test_stale_camera_returns_no_frame(settings):
    cam = CameraReader(settings, capture_factory=lambda: None)
    assert cam.latest() is None
