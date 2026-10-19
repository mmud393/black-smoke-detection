"""Measure real detector latency, CPU time and RAM on this host (synthetic frame)."""
import resource
import sys
import time

import _path  # noqa: F401
import numpy as np

from smoke_monitor.config import load_config
from smoke_monitor.detector import MotionSmokeDetector

cfg = load_config(check_placeholders=False, require_smtp=False, require_ai=False)
det = MotionSmokeDetector(cfg.dark_luminance, cfg.min_blob_fraction, cfg.detection_roi)
rng = np.random.default_rng(0)
frame = rng.integers(100, 140, (1080, 1920, 3), dtype=np.uint8)
for _ in range(det.warmup_frames + 1):
    det.detect(frame)
n, cpu0, t0 = 100, time.process_time(), time.time()
lat = []
for _ in range(n):
    s = time.time()
    det.detect(frame)
    lat.append(time.time() - s)
wall, cpu = time.time() - t0, time.process_time() - cpu0
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1 if sys.platform == "darwin" else 1024) / 1e6
print(f"mean latency={np.mean(lat) * 1000:.1f}ms p95={np.percentile(lat, 95) * 1000:.1f}ms "
      f"=> max ~{1 / np.mean(lat):.1f} frames/s; CPU-seconds per wall-second={cpu / wall:.2f}; peak RSS~{rss:.0f} MB")
print(f"Configured INFERENCE_FPS={cfg.inference_fps}: " +
      ("OK" if 1 / np.mean(lat) >= cfg.inference_fps else "TOO HIGH for this host - lower it"))
print("Note: synthetic frame; the Claude API call is not included (it runs only per candidate episode).")
