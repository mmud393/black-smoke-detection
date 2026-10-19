import time

import numpy as np

from smoke_monitor.camera import CameraReader, Frame, LatestFrameBuffer


class FakeCap:
    def __init__(self, ok_open=True, frames=3):
        self.ok_open, self.frames, self.released = ok_open, frames, False

    def isOpened(self):
        return self.ok_open

    def read(self):
        if self.frames > 0:
            self.frames -= 1
            return True, np.zeros((10, 10, 3), np.uint8)
        return False, None

    def release(self):
        self.released = True


def test_buffer_keeps_only_latest():
    b = LatestFrameBuffer()
    for i in range(5):
        b.put(Frame(np.zeros((1, 1, 3), np.uint8), time.monotonic(), i))
    assert b.get().seq == 4


def test_reconnects_after_failure_and_stall():
    caps = [FakeCap(ok_open=False), FakeCap(frames=2), FakeCap(frames=2)]
    made = []

    def factory():
        c = caps[len(made)] if len(made) < len(caps) else FakeCap(frames=1)
        made.append(c)
        return c

    r = CameraReader("rtsp://x", "redacted", stall_timeout=0.2, capture_factory=factory,
                     sleep=lambda s: time.sleep(0.01))
    r.start()
    deadline = time.time() + 5
    while len(made) < 3 and time.time() < deadline:
        time.sleep(0.05)
    r.stop()
    assert len(made) >= 3 and r.reconnects >= 2
    assert all(c.released for c in made[:3]) and r.status == "stopped"


def test_stale_buffer_cleared_on_disconnect():
    r = CameraReader("rtsp://x", "redacted", stall_timeout=0.1,
                     capture_factory=lambda: FakeCap(frames=1), sleep=lambda s: time.sleep(0.2))
    r.start()
    time.sleep(0.6)
    r.stop()
    assert r.buffer.get() is None and r.frame_age() is None
