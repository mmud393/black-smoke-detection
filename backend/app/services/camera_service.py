from __future__ import annotations

from datetime import datetime
from pathlib import Path

from smoke_shared.config import Settings
from smoke_shared.crypto import SecretBox
from smoke_shared.db import models as m
from smoke_shared.db import utcnow
from smoke_shared.enums import CameraStatus
from smoke_shared.urls import SourceError, validate_rtsp

from ..errors import ApiError
from ..schemas.camera import CameraOut


def validate_source(settings: Settings, kind: str, source: str) -> str:
    """Returns sanitized endpoint or raises ApiError(422)."""
    try:
        if kind == "RTSP":
            cidrs = [c.strip() for c in settings.camera_allowed_cidrs.split(",") if c.strip()]
            return validate_rtsp(source, cidrs or None)
        if kind == "VIDEO_FILE":
            p = Path(source).resolve()
            roots = [(settings.data_dir / "videos").resolve(), (settings.data_dir.parent / "fixtures").resolve()]
            if not any(p.is_relative_to(r) for r in roots):
                raise SourceError("video files must be inside DATA_DIR/videos or fixtures/")
            if not p.is_file():
                raise SourceError("video file not found")
            return f"file:{p.name}"
        if kind == "TEST_FAKE":
            if not settings.demo_mode:
                raise SourceError("TEST_FAKE sources require DEMO_MODE=true")
            return "TEST-ONLY synthetic source"
        raise SourceError("unsupported source kind")
    except SourceError as exc:
        raise ApiError(422, "INVALID_SOURCE", str(exc)) from None


def to_out(cam: m.Camera, st: m.CameraStatusRow | None, stale_after: float) -> CameraOut:
    now = utcnow()
    age = (now - st.preview_timestamp).total_seconds() if st and st.preview_timestamp else None
    status = cam.enabled and (st.connectivity if st else CameraStatus.CONNECTING.value) or CameraStatus.DISABLED.value
    # Never show a stale ONLINE: if the worker has not updated status recently, say so.
    if status == "ONLINE" and st and st.worker_heartbeat_at and (now - st.worker_heartbeat_at).total_seconds() > stale_after * 3:
        status = "OFFLINE"
    iso = lambda d: d.isoformat() if isinstance(d, datetime) else None  # noqa: E731
    return CameraOut(
        id=cam.id, name=cam.name, zone=cam.zone, location_description=cam.location_description,
        source_kind=cam.source_kind, enabled=cam.enabled, status=status, sanitizedEndpoint=cam.sanitized_endpoint,
        lastFrameAt=iso(st.last_frame_at) if st else None, lastInferenceAt=iso(st.last_inference_at) if st else None,
        snapshotUrl=f"/api/v1/cameras/{cam.id}/snapshot.jpg" if age is not None else None,
        previewAgeSeconds=round(age, 1) if age is not None else None,
        transport=cam.transport, capture_fps_limit=cam.capture_fps_limit,
        inference_fps_target=cam.inference_fps_target, preview_fps=cam.preview_fps, max_width=cam.max_width,
        roi_polygons=cam.roi_polygons or [], ignore_polygons=cam.ignore_polygons or [],
        detection_profile_id=cam.detection_profile_id,
        captureFps=st.capture_fps if st else None, inferenceFps=st.inference_fps if st else None,
        inferenceLatencyMs=st.inference_latency_ms if st else None,
        reconnectCount=st.reconnect_count if st else 0, lastErrorCode=st.last_error_code if st else None,
        statusReason=st.last_transition_reason if st else None, updated_at=cam.updated_at.isoformat(),
    )


def encrypt_source(box: SecretBox, source: str) -> str:
    return box.encrypt(source)
