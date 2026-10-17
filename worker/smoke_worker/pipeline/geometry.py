"""ROI / ignore-zone filtering and coordinate mapping. All polygons are normalized 0..1."""

from __future__ import annotations

import numpy as np

Box = tuple[int, int, int, int]  # x1,y1,x2,y2 in ORIGINAL frame pixels


def polys_to_mask(polys: list[list[list[float]]], width: int, height: int) -> np.ndarray:
    import cv2

    mask = np.zeros((height, width), np.uint8)
    for poly in polys:
        pts = np.array([[round(x * (width - 1)), round(y * (height - 1))] for x, y in poly], np.int32)
        cv2.fillPoly(mask, [pts], 255)
    return mask


def clip_box(box: Box, width: int, height: int) -> Box:
    x1, y1, x2, y2 = box
    return max(0, min(x1, width - 1)), max(0, min(y1, height - 1)), max(0, min(x2, width)), max(0, min(y2, height))


def scale_box(box_xyxy: tuple[float, float, float, float], src_size: tuple[int, int], dst_size: tuple[int, int]) -> Box:
    """Map a box from an inference-resized image (w,h) back to original frame (w,h)."""
    sx, sy = dst_size[0] / src_size[0], dst_size[1] / src_size[1]
    x1, y1, x2, y2 = box_xyxy
    return int(round(x1 * sx)), int(round(y1 * sy)), int(round(x2 * sx)), int(round(y2 * sy))


def box_area(b: Box) -> int:
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def iou(a: Box, b: Box) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = box_area(a) + box_area(b) - inter
    return inter / union if union else 0.0


def overlap_fraction(box: Box, mask: np.ndarray) -> float:
    """Fraction of the box area covered by a binary mask."""
    x1, y1, x2, y2 = box
    region = mask[y1:y2, x1:x2]
    return float((region > 0).mean()) if region.size else 0.0


def nms(boxes: list[Box], scores: list[float], iou_thr: float = 0.5) -> list[int]:
    order = sorted(range(len(boxes)), key=lambda i: -scores[i])
    keep: list[int] = []
    for i in order:
        if all(iou(boxes[i], boxes[j]) < iou_thr for j in keep):
            keep.append(i)
    return keep
