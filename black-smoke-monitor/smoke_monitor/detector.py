"""Pretrained Grounding DINO Tiny inference (no training), plus box utilities."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

# Labels that must never become a smoke alert on their own.
REJECT_LABELS = ("fire", "flame", "person", "people", "car", "vehicle", "truck", "steam")


@dataclass(frozen=True)
class Detection:
    box: tuple[int, int, int, int]  # x1, y1, x2, y2 in ORIGINAL frame pixels
    score: float
    label: str


def clip_box(box, width: int, height: int, min_size: int = 8):
    """Clip to the frame; return None if invalid, outside, or too small."""
    x1, y1, x2, y2 = (float(v) for v in box)
    if not all(np.isfinite([x1, y1, x2, y2])):
        return None
    x1, x2 = sorted((x1, x2))
    y1, y2 = sorted((y1, y2))
    x1, y1 = max(0.0, x1), max(0.0, y1)
    x2, y2 = min(float(width), x2), min(float(height), y2)
    if x2 - x1 < min_size or y2 - y1 < min_size:
        return None
    return int(x1), int(y1), int(x2), int(y2)


def scale_box(box, scale_x: float, scale_y: float):
    """Map a box from resized-inference coordinates back to the full frame."""
    x1, y1, x2, y2 = box
    return x1 * scale_x, y1 * scale_y, x2 * scale_x, y2 * scale_y


def normalize_prompt(prompt: str) -> str:
    """Grounding DINO wants lowercase phrases ending with a period."""
    p = prompt.strip().lower()
    return p if p.endswith(".") else p + "."


class GroundingDinoDetector:
    def __init__(self, model_dir: Path, prompt: str, box_threshold: float,
                 text_threshold: float, device: str = "cpu", max_side: int = 800):
        import torch
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

        model_dir = Path(model_dir)
        if not (model_dir / "config.json").exists():
            raise FileNotFoundError(
                f"Model not found in {model_dir}. Run: python scripts/download_model.py")
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("DEVICE=cuda requested but CUDA is not available")
        self.torch = torch
        self.device = device
        self.prompt = normalize_prompt(prompt)
        self.box_threshold, self.text_threshold = box_threshold, text_threshold
        self.max_side = max_side
        self.processor = AutoProcessor.from_pretrained(str(model_dir), local_files_only=True)
        self.model = AutoModelForZeroShotObjectDetection.from_pretrained(
            str(model_dir), local_files_only=True).to(device).eval()
        log.info("Loaded model from %s on %s", model_dir, device)

    def warmup(self, shape=(480, 640, 3)) -> None:
        self.detect(np.full(shape, 128, dtype=np.uint8))

    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        import cv2
        from PIL import Image

        h, w = frame_bgr.shape[:2]
        scale = min(1.0, self.max_side / max(h, w))
        small = cv2.resize(frame_bgr, (int(w * scale), int(h * scale))) if scale < 1 else frame_bgr
        rgb = Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
        inputs = self.processor(images=rgb, text=self.prompt, return_tensors="pt").to(self.device)
        with self.torch.inference_mode():
            outputs = self.model(**inputs)
        res = self.processor.post_process_grounded_object_detection(
            outputs, inputs.input_ids, threshold=self.box_threshold,
            text_threshold=self.text_threshold, target_sizes=[(small.shape[0], small.shape[1])],
        )[0]
        labels = res.get("text_labels", res.get("labels", []))
        out: list[Detection] = []
        for box, score, label in zip(res["boxes"].tolist(), res["scores"].tolist(), labels):
            label = str(label).lower()
            if any(r in label for r in REJECT_LABELS) and "smoke" not in label:
                continue
            clipped = clip_box(scale_box(box, w / small.shape[1], h / small.shape[0]), w, h)
            if clipped:
                out.append(Detection(clipped, float(score), label))
        return out


class StubDetector:
    """TEST-ONLY detector returning a fixed box. Never used unless explicitly requested
    (scripts/replay_video.py --stub-detector). The monitor never constructs it."""

    def __init__(self, box=(10, 10, 100, 100), score: float = 0.9, label: str = "stub smoke"):
        self.box, self.score, self.label = box, score, label
        self.enabled = True

    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        if not self.enabled:
            return []
        h, w = frame_bgr.shape[:2]
        b = clip_box(self.box, w, h)
        return [Detection(b, self.score, self.label)] if b else []
