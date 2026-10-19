import numpy as np

from smoke_monitor.detector import MotionSmokeDetector


def scene(bg=170):
    return np.full((240, 320, 3), bg, np.uint8)


def learned(det, bg=170, n=30):
    for _ in range(n):
        det.detect(scene(bg))


def test_new_dark_blob_is_detected_with_full_frame_box():
    det = MotionSmokeDetector(warmup_frames=10)
    learned(det)
    img = scene()
    img[60:140, 100:200] = 30
    boxes = [d.box for d in det.detect(img)]
    assert len(boxes) == 1
    x1, y1, x2, y2 = boxes[0]
    assert abs(x1 - 100) < 12 and abs(x2 - 200) < 12 and abs(y1 - 60) < 12 and abs(y2 - 140) < 12


def test_white_steam_blob_is_not_detected():
    det = MotionSmokeDetector(warmup_frames=10)
    learned(det, bg=120)
    img = scene(120)
    img[60:140, 100:200] = 240
    assert det.detect(img) == []


def test_dark_object_present_from_start_is_background():
    det = MotionSmokeDetector(warmup_frames=10)
    img = scene()
    img[60:140, 100:200] = 30
    for _ in range(40):
        assert det.detect(img) == [] or det.frames_seen <= 10
    assert det.detect(img) == []


def test_whole_scene_change_is_ignored():
    det = MotionSmokeDetector(warmup_frames=10)
    learned(det)
    assert det.detect(scene(40)) == []


def test_warmup_reports_nothing_and_roi_limits_area():
    det = MotionSmokeDetector(warmup_frames=10, roi=((0.0, 0.0), (0.4, 0.0), (0.4, 1.0), (0.0, 1.0)))
    assert det.detect(scene()) == []
    learned(det)
    img = scene()
    img[60:140, 220:300] = 30           # outside the ROI (right side)
    assert det.detect(img) == []
    img = scene()
    img[60:140, 20:100] = 30            # inside the ROI
    assert len(det.detect(img)) == 1
