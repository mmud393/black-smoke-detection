import numpy as np

from smoke_monitor.detector import clip_box, scale_box
from smoke_monitor.verifier import analyze_region

BOX = (100, 100, 200, 200)


def scene(bg=160, region=40, noise=0, seed=0):
    img = np.full((300, 300, 3), bg, np.uint8)
    img[100:200, 100:200] = region
    if noise:
        rng = np.random.default_rng(seed)
        img = np.clip(img.astype(int) + rng.integers(-noise, noise, img.shape), 0, 255).astype(np.uint8)
    return img


def moving_dark(prev):
    """Dark plume whose shape changed: a chunk of the box flips between dark and mid-gray."""
    cur = prev.copy()
    cur[100:200, 100:140] = 120
    return cur


def test_clip_and_scale_boxes():
    assert clip_box((-20, -5, 50, 60), 100, 100) == (0, 0, 50, 60)
    assert clip_box((500, 500, 600, 600), 100, 100) is None
    assert clip_box((10, 10, 12, 12), 100, 100) is None
    assert clip_box((float("nan"), 0, 5, 5), 100, 100) is None
    assert scale_box((10, 20, 30, 40), 2.0, 3.0) == (20.0, 60.0, 60.0, 120.0)


def test_moving_dark_region_is_dark_smoke():
    prev = scene()
    assert analyze_region(moving_dark(prev), BOX, prev).verdict == "dark_smoke"


def test_darkness_alone_is_not_enough_static_object():
    prev = scene()
    ap = analyze_region(prev.copy(), BOX, prev)
    assert ap.dark_fraction > 0.9 and ap.verdict == "static_dark"


def test_white_steam_rejected():
    prev = scene(bg=120, region=230)
    cur = prev.copy()
    cur[100:200, 100:140] = 200
    ap = analyze_region(cur, BOX, prev)
    assert ap.verdict == "white_smoke"


def test_camera_shake_is_uncertain():
    prev = scene(noise=40, seed=1)
    cur = scene(noise=40, seed=2)
    assert analyze_region(cur, BOX, prev).verdict == "uncertain"


def test_no_previous_frame_is_uncertain():
    assert analyze_region(scene(), BOX, None).verdict == "uncertain"
