"""Offline replay of a video file through the real pipeline; prints a JSON summary.
Email is never sent. Claude confirms alerts when ANTHROPIC_API_KEY is set (costs API calls);
--stub-detector and --no-ai are TEST-ONLY switches for end-to-end flow checks."""
import argparse
import json
import tempfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import _path  # noqa: F401
import cv2

from smoke_monitor.config import load_config
from smoke_monitor.email_alert import build_message
from smoke_monitor.monitor import Monitor
from smoke_monitor.verifier import analyze_region

ap = argparse.ArgumentParser()
ap.add_argument("--video", required=True)
ap.add_argument("--fps", type=float, default=None, help="sampling rate (default INFERENCE_FPS)")
ap.add_argument("--dry-run-email", action="store_true", help="compose the email, do not send")
ap.add_argument("--stub-detector", action="store_true", help="TEST-ONLY fixed-box detector")
ap.add_argument("--no-ai", action="store_true", help="TEST-ONLY: skip Claude, confirm every episode")
ap.add_argument("--out", default=None, help="screenshot dir (default: temp dir)")
a = ap.parse_args()

cfg = load_config(check_placeholders=False, require_smtp=False, require_ai=not a.no_ai)
out = Path(a.out or tempfile.mkdtemp(prefix="replay_"))
cfg = replace(cfg, data_dir=out)
if a.stub_detector:
    from smoke_monitor.detector import StubDetector
    det = StubDetector(box=(0, 0, 10 ** 6, 10 ** 6))
    print("WARNING: TEST-ONLY stub detector in use")
else:
    from smoke_monitor.detector import MotionSmokeDetector
    det = MotionSmokeDetector(cfg.dark_luminance, cfg.min_blob_fraction, cfg.detection_roi)

if a.no_ai:
    from smoke_monitor.ai_confirm import AIVerdict

    class _Yes:
        def confirm(self, path):
            return AIVerdict(True, "yes", "TEST-ONLY: AI skipped")
    confirmer = _Yes()
    print("WARNING: TEST-ONLY --no-ai: every episode is auto-confirmed")
else:
    from smoke_monitor.ai_confirm import ClaudeConfirmer
    confirmer = ClaudeConfirmer(cfg.anthropic_api_key, cfg.ai_model, cfg.ai_timeout)

class _Once:
    """Run the (stateful) detector once per frame; process_frame reuses the result."""
    def __init__(self, inner):
        self.inner, self._img, self._res = inner, None, []

    def detect(self, img):
        if img is not self._img:
            self._img, self._res = img, self.inner.detect(img)
        return self._res


det = _Once(det)


class NoEmail:
    def notify(self): pass
    def start(self): pass
    def stop(self): pass

mon = Monitor(cfg, det, confirmer, reader=object(), email_worker=NoEmail())
cap = cv2.VideoCapture(a.video)
src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
step = max(1, round(src_fps / (a.fps or cfg.inference_fps)))
decisions, alerts, i = [], [], 0
while True:
    ok, img = cap.read()
    if not ok:
        break
    if i % step == 0:
        t = i / src_fps
        dets = det.detect(img)
        cands = []
        for d in dets:
            ap_ = analyze_region(img, d.box, mon._prev_gray, cfg.dark_luminance,
                                 cfg.min_dark_fraction, cfg.min_motion_fraction)
            cands.append({"box": d.box, "score": round(d.score, 3), "label": d.label,
                          "verdict": ap_.verdict, "reason": ap_.reason})
        shot = mon.process_frame(img, t)  # reuses the detections above
        decisions.append({"t": round(t, 2), "candidates": cands})
        if shot:
            alerts.append({"t": round(t, 2), "screenshot": shot})
    i += 1
summary = {"video": a.video, "frames_read": i, "sampled": len(decisions),
           "alerts": alerts, "decisions": decisions, "email_sent": False}
msgs = []
if a.dry_run_email:
    for al in alerts:
        m = build_message(cfg if cfg.alert_to else replace(cfg, alert_to=("dry@run.local",)),
                          Path(al["screenshot"]), datetime.now(timezone.utc))
        msgs.append({"subject": m["Subject"], "attachments": [p.get_filename() for p in m.iter_attachments()]})
    summary["dry_run_emails"] = msgs
print(json.dumps(summary, indent=2))
