"""ONNX smoke model (YOLO), black/motion verification inside the candidate box, event tracking."""
from __future__ import annotations

import ast
import logging
import math
import shutil
import tarfile
from pathlib import Path
from collections import deque
from dataclasses import dataclass

import cv2
import numpy as np

from config import Settings

log = logging.getLogger("detector")

NMS_IOU = 0.45  # algorithm constant for overlapping YOLO boxes


class ModelError(RuntimeError):
    pass


@dataclass(frozen=True)
class Candidate:
    box: tuple  # x1, y1, x2, y2 in processed-frame pixels
    confidence: float


@dataclass(frozen=True)
class Verdict:
    positive: bool
    candidate: Candidate | None = None
    dark_ratio: float = 0.0
    motion_ratio: float = 0.0


def ensure_model(s: Settings) -> None:
    """Download the model artifact only when missing (a .tar.gz is unpacked to MODEL_PATH)."""
    if s.model_path.exists():
        return
    s.model_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from huggingface_hub import hf_hub_download
        got = Path(hf_hub_download(repo_id=s.model_repo_id, filename=s.model_filename,
                                   local_dir=s.model_path.parent))
        if got.name.endswith((".tar.gz", ".tgz")):
            with tarfile.open(got) as tar:
                members = [m for m in tar.getmembers() if m.isfile() and m.name.endswith(".onnx")]
                if len(members) != 1:
                    raise ModelError("archive must contain exactly one .onnx file")
                with tar.extractfile(members[0]) as src, open(s.model_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        elif got.resolve() != s.model_path.resolve():
            shutil.move(got, s.model_path)
    except Exception as exc:
        raise ModelError(
            f"Model {s.model_repo_id}/{s.model_filename} is missing at {s.model_path} and could not be "
            f"set up ({type(exc).__name__}). Check internet access and the repo, or place the .onnx file there."
        ) from exc


class SmokeModel:
    """Ultralytics-style YOLO ONNX detector: output (1, 4+num_classes, anchors), xywh in input pixels."""

    def __init__(self, s: Settings, session=None):
        self._s = s
        if session is None:
            import onnxruntime as ort
            session = ort.InferenceSession(str(s.model_path), providers=["CPUExecutionProvider"])
        self._sess = session
        self._in_name = session.get_inputs()[0].name
        self._size = 1024  # trained/exported image size; plain resize, as in the model card
        meta = getattr(session, "get_modelmeta", lambda: None)()
        names = _parse_names((meta.custom_metadata_map if meta else {}).get("names"))
        if names is not None:
            if s.model_smoke_class_name not in names.values():
                raise ModelError(f"MODEL_SMOKE_CLASS_NAME {s.model_smoke_class_name!r} not in model classes {names}")
            self._class_idx = next(k for k, v in names.items() if v == s.model_smoke_class_name)
        else:
            self._class_idx = 0

    def detect(self, bgr: np.ndarray) -> list[Candidate]:
        """Smoke-class detections >= MODEL_CONFIDENCE_MIN, boxes in `bgr` pixel coordinates."""
        h, w = bgr.shape[:2]
        rgb = cv2.cvtColor(cv2.resize(bgr, (self._size, self._size)), cv2.COLOR_BGR2RGB)
        x = (rgb.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
        out = np.asarray(self._sess.run(None, {self._in_name: x})[0])
        if out.ndim != 3 or out.shape[1] < 5 or self._class_idx + 4 >= out.shape[1]:
            raise ModelError(f"Unexpected ONNX output shape {out.shape}; expected (1, 4+classes, anchors)")
        pred = out[0]
        scores = pred[4 + self._class_idx]
        keep = np.flatnonzero(np.isfinite(scores) & (scores >= self._s.model_confidence_min))
        boxes, confs = [], []
        sx, sy = w / self._size, h / self._size
        for i in keep:
            cx, cy, bw, bh = (float(v) for v in pred[:4, i])
            box = clip_box((cx - bw / 2) * sx, (cy - bh / 2) * sy, (cx + bw / 2) * sx, (cy + bh / 2) * sy, w, h)
            if box is not None:
                boxes.append([box[0], box[1], box[2] - box[0], box[3] - box[1]])
                confs.append(float(scores[i]))
        if not boxes:
            return []
        idx = np.array(cv2.dnn.NMSBoxes(boxes, confs, self._s.model_confidence_min, NMS_IOU)).flatten()
        return [Candidate((boxes[i][0], boxes[i][1], boxes[i][0] + boxes[i][2], boxes[i][1] + boxes[i][3]), confs[i])
                for i in idx]


def _parse_names(raw):
    if not raw:
        return None
    try:
        names = ast.literal_eval(raw)
        return {int(k): str(v) for k, v in names.items()}
    except (ValueError, SyntaxError, AttributeError):
        return None


def clip_box(x1, y1, x2, y2, w, h):
    """Clipped int box, or None for NaN/inf/empty/out-of-frame boxes."""
    if not all(math.isfinite(v) for v in (x1, y1, x2, y2)):
        return None
    x1, y1, x2, y2 = max(0, int(x1)), max(0, int(y1)), min(w, int(x2)), min(h, int(y2))
    return (x1, y1, x2, y2) if x2 > x1 and y2 > y1 else None


class BlackSmokeVerifier:
    """Darkness + motion checks inside a model smoke box. Never fires on a dark frame alone."""

    def __init__(self, s: Settings):
        self._s = s
        self._prev_gray: np.ndarray | None = None
        self._prev_conn: int | None = None

    def reset(self) -> None:
        self._prev_gray = None

    def evaluate(self, frame: np.ndarray, candidates: list[Candidate], connection_id: int) -> Verdict:
        s = self._s
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        prev = self._prev_gray
        if connection_id != self._prev_conn or prev is None or prev.shape != gray.shape:
            prev = None  # first frame after (re)connect is a reference, not motion
        self._prev_gray, self._prev_conn = gray, connection_id
        best = Verdict(False)
        if prev is None:
            return best
        diff = cv2.absdiff(gray, prev)
        for c in candidates:
            x1, y1, x2, y2 = c.box
            if (x2 - x1) * (y2 - y1) < s.smoke_region_min_area_px:
                continue
            moving = diff[y1:y2, x1:x2] >= s.motion_pixel_difference_min
            motion_ratio = float(moving.mean())
            region = gray[y1:y2, x1:x2]
            fg = region[moving]
            # Darkness is judged on the moving part so a dark static background cannot pass.
            dark_ratio = float((fg <= s.black_luma_max).mean()) if fg.size else 0.0
            ok = motion_ratio >= s.motion_pixel_ratio_min and dark_ratio >= s.black_dark_pixel_ratio_min
            if ok and (not best.positive or c.confidence > best.candidate.confidence):
                best = Verdict(True, c, dark_ratio, motion_ratio)
        return best


class EventTracker:
    """Multi-frame confirmation, one alert per episode, clear timer and cooldown."""

    def __init__(self, s: Settings):
        self._s = s
        self._window: deque[bool] = deque(maxlen=s.confirmation_window_frames)
        self.active = False
        self._last_positive = 0.0
        self._last_alert: float | None = None
        self._lost = False

    def camera_lost(self) -> None:
        """A dropped camera is an unknown state, not proof the smoke cleared."""
        self._lost = True

    def observe(self, positive: bool, now: float) -> bool:
        """Record one valid inference result. Returns True when a new alert should be sent."""
        s = self._s
        if self._lost:
            self._lost = False
            if self.active:
                self._last_positive = now  # restart the clear timer after an outage
        self._window.append(positive)
        if positive:
            self._last_positive = now
        if self.active:
            if now - self._last_positive >= s.event_clear_seconds:
                self.active = False
                self._window.clear()
            return False
        if sum(self._window) >= s.confirmation_positive_frames:
            self.active = True
            self._last_positive = now
            if self._last_alert is None or now - self._last_alert >= s.email_cooldown_seconds:
                self._last_alert = now
                return True
        return False
