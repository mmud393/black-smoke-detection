"""Measure real inference latency, CPU time and RAM on this host (synthetic frame)."""
import resource
import sys
import time

import _path  # noqa: F401
import numpy as np

from smoke_monitor.config import load_config
from smoke_monitor.detector import GroundingDinoDetector

cfg = load_config(check_placeholders=False, require_smtp=False)
det = GroundingDinoDetector(cfg.model_local_dir, cfg.detection_prompt, cfg.box_threshold,
                            cfg.text_threshold, cfg.device)
frame = np.random.default_rng(0).integers(0, 255, (1080, 1920, 3), dtype=np.uint8)
det.detect(frame)  # warm-up
n, cpu0, t0 = 10, time.process_time(), time.time()
lat = []
for _ in range(n):
    s = time.time()
    det.detect(frame)
    lat.append(time.time() - s)
wall, cpu = time.time() - t0, time.process_time() - cpu0
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1 if sys.platform == "darwin" else 1024) / 1e6
print(f"device={cfg.device} mean latency={np.mean(lat):.2f}s p95={np.percentile(lat, 95):.2f}s "
      f"=> max ~{1 / np.mean(lat):.2f} inferences/s; CPU-seconds per wall-second={cpu / wall:.2f}; peak RSS~{rss:.0f} MB")
print(f"Configured INFERENCE_FPS={cfg.inference_fps}: " +
      ("OK" if 1 / np.mean(lat) >= cfg.inference_fps else "TOO HIGH for this host - lower it"))
print("Note: synthetic frame; real scenes (and candidate count) may differ.")
