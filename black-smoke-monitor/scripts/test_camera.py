"""Verify the Dahua RTSP stream connects and decodes fresh frames."""
import time

import _path  # noqa: F401
import cv2

from smoke_monitor.camera import open_capture
from smoke_monitor.config import load_config

cfg = load_config(check_placeholders=True, require_smtp=False)
print("Connecting to", cfg.redacted_url)
cap = open_capture(cfg.rtsp_url, cfg.rtsp_transport, cfg.connect_timeout)
if not cap.isOpened():
    raise SystemExit("FAILED to open stream. Check IP/port/credentials, RTSP enabled, VLC test, firewall.")
n, t0 = 0, time.time()
while n < 30 and time.time() - t0 < 30:
    ok, img = cap.read()
    if ok:
        n += 1
        last = img
cap.release()
if n == 0:
    raise SystemExit("Opened but no frames decoded (try H.264 and subtype=1).")
out = cfg.data_dir / "test_frame.jpg"
out.parent.mkdir(parents=True, exist_ok=True)
cv2.imwrite(str(out), last)
print(f"OK: decoded {n} frames, size {last.shape[1]}x{last.shape[0]}, ~{n / (time.time() - t0):.1f} fps. Saved {out}")
