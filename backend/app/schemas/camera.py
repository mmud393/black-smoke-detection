from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Polygon = list[list[float]]


def _check_polys(v: list[Polygon]) -> list[Polygon]:
    for poly in v:
        if len(poly) < 3:
            raise ValueError("polygon needs >= 3 points")
        for pt in poly:
            if len(pt) != 2 or not all(0.0 <= c <= 1.0 for c in pt):
                raise ValueError("polygon points must be normalized [x,y] in 0..1")
    return v


class CameraIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    zone: str = Field("", max_length=100)
    location_description: str = Field("", max_length=300)
    source_kind: Literal["RTSP", "VIDEO_FILE", "TEST_FAKE"] = "RTSP"
    source: str = Field(min_length=1, max_length=1000, description="RTSP URL or video file path (write-only)")
    transport: Literal["tcp", "udp"] = "tcp"
    enabled: bool = False
    capture_fps_limit: float = Field(5.0, gt=0, le=30)
    inference_fps_target: float = Field(1.0, gt=0, le=10)
    preview_fps: float = Field(1.0, gt=0, le=5)
    max_width: int = Field(1280, ge=160, le=3840)
    roi_polygons: list[Polygon] = []
    ignore_polygons: list[Polygon] = []
    detection_profile_id: str | None = None

    _p = field_validator("roi_polygons", "ignore_polygons")(_check_polys)


class CameraPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    zone: str | None = None
    location_description: str | None = None
    source: str | None = Field(None, min_length=1, max_length=1000)  # omitted = unchanged
    transport: Literal["tcp", "udp"] | None = None
    enabled: bool | None = None
    capture_fps_limit: float | None = Field(None, gt=0, le=30)
    inference_fps_target: float | None = Field(None, gt=0, le=10)
    preview_fps: float | None = Field(None, gt=0, le=5)
    max_width: int | None = Field(None, ge=160, le=3840)
    roi_polygons: list[Polygon] | None = None
    ignore_polygons: list[Polygon] | None = None
    detection_profile_id: str | None = None
    expected_updated_at: str | None = None  # optimistic concurrency

    _p = field_validator("roi_polygons", "ignore_polygons")(lambda v: _check_polys(v) if v is not None else v)


class CameraOut(BaseModel):
    id: str
    name: str
    zone: str
    location_description: str
    source_kind: str
    enabled: bool
    status: str
    sanitizedEndpoint: str
    lastFrameAt: str | None
    lastInferenceAt: str | None
    snapshotUrl: str | None
    previewAgeSeconds: float | None
    transport: str
    capture_fps_limit: float
    inference_fps_target: float
    preview_fps: float
    max_width: int
    roi_polygons: list
    ignore_polygons: list
    detection_profile_id: str | None
    captureFps: float | None = None
    inferenceFps: float | None = None
    inferenceLatencyMs: float | None = None
    reconnectCount: int = 0
    lastErrorCode: str | None = None
    statusReason: str | None = None
    updated_at: str


class TestConnectionIn(BaseModel):
    source_kind: Literal["RTSP", "VIDEO_FILE"] = "RTSP"
    source: str = Field(min_length=1, max_length=1000)
    transport: Literal["tcp", "udp"] = "tcp"


class CameraAction(BaseModel):
    action: Literal["start", "pause", "restart", "disable"]
