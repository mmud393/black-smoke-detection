from __future__ import annotations

import time
from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request, Response
from smoke_shared.db import models as m
from smoke_shared.db import utcnow
from smoke_shared.probe import probe_source
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import Principal, admin, client_ip, get_box, operator, viewer
from ..errors import ApiError
from ..schemas.camera import CameraAction, CameraIn, CameraOut, CameraPatch, TestConnectionIn
from ..services.audit import audit, event
from ..services.camera_service import to_out, validate_source

router = APIRouter(prefix="/api/v1/cameras", tags=["cameras"])
_last_test: dict[str, float] = {}


def _get(db: Session, cid: str) -> m.Camera:
    cam = db.get(m.Camera, cid)
    if not cam or cam.archived_at:
        raise ApiError(404, "NOT_FOUND", "Camera not found.")
    return cam


def _out(request: Request, db: Session, cam: m.Camera) -> CameraOut:
    st = db.get(m.CameraStatusRow, cam.id)
    return to_out(cam, st, request.app.state.settings.camera_stale_seconds)


def _command(db: Session, target: str, command: str, user: str | None, args: dict | None = None) -> None:
    db.add(m.WorkerCommand(target=target, command=command, args=args or {}, requested_by=user))


@router.get("")
def list_cameras(request: Request, limit: int = Query(50, ge=1, le=200), cursor: str | None = None,
                 status: str | None = None, query: str | None = None, _: Principal = Depends(viewer),
                 db: Session = Depends(get_db)) -> dict:
    q = select(m.Camera).where(m.Camera.archived_at.is_(None)).order_by(m.Camera.name, m.Camera.id)
    if query:
        q = q.where(m.Camera.name.ilike(f"%{query}%") | m.Camera.zone.ilike(f"%{query}%"))
    if cursor:
        q = q.where(m.Camera.name > cursor)
    rows = db.execute(q.limit(limit + 1)).scalars().all()
    items = [_out(request, db, c) for c in rows[:limit]]
    if status:
        items = [i for i in items if i.status == status]
    return {"items": items, "next_cursor": rows[limit - 1].name if len(rows) > limit else None}


@router.post("", response_model=CameraOut, status_code=201)
def create_camera(body: CameraIn, request: Request, p: Principal = Depends(admin), db: Session = Depends(get_db),
                  box=Depends(get_box)) -> CameraOut:
    s = request.app.state.settings
    endpoint = validate_source(s, body.source_kind, body.source)
    cam = m.Camera(**body.model_dump(exclude={"source"}), source_enc=box.encrypt(body.source),
                   sanitized_endpoint=endpoint)
    db.add(cam)
    db.flush()
    db.add(m.CameraStatusRow(camera_id=cam.id, connectivity="CONNECTING" if cam.enabled else "DISABLED",
                             last_transition_at=utcnow(), last_transition_reason="created"))
    audit(db, p.user.id, "camera.create", "camera", cam.id, {"name": cam.name, "endpoint": endpoint}, client_ip(request))
    event(db, "camera.created", camera_id=cam.id, actor=p.user.id)
    if cam.enabled:
        _command(db, cam.id, "reload", p.user.id)
    db.commit()
    return _out(request, db, cam)


@router.post("/test-connection")
def test_connection(body: TestConnectionIn, request: Request, p: Principal = Depends(admin)) -> dict:
    s = request.app.state.settings
    validate_source(s, body.source_kind, body.source)
    now = time.monotonic()
    if now - _last_test.get(p.user.id, 0) < 3:  # throttle: one test / 3 s / admin
        raise ApiError(429, "RATE_LIMITED", "Please wait before testing again.")
    _last_test[p.user.id] = now
    return probe_source(body.source, body.transport, 10.0).dict()


@router.get("/{camera_id}", response_model=CameraOut)
def get_camera(camera_id: str, request: Request, _: Principal = Depends(viewer), db: Session = Depends(get_db)):
    return _out(request, db, _get(db, camera_id))


@router.patch("/{camera_id}", response_model=CameraOut)
def patch_camera(camera_id: str, body: CameraPatch, request: Request, p: Principal = Depends(admin),
                 db: Session = Depends(get_db)) -> CameraOut:
    cam = _get(db, camera_id)
    if body.expected_updated_at and body.expected_updated_at != cam.updated_at.isoformat():
        raise ApiError(409, "CONFLICT", "Camera was modified by someone else; reload and retry.")
    data = body.model_dump(exclude_unset=True, exclude={"expected_updated_at", "source"})
    if "source" in body.model_fields_set and body.source:
        cam.sanitized_endpoint = validate_source(request.app.state.settings, cam.source_kind, body.source)
        cam.source_enc = get_box(request).encrypt(body.source)
    for k, v in data.items():
        setattr(cam, k, v)
    audit(db, p.user.id, "camera.update", "camera", cam.id, {"fields": sorted(data) + (["source"] if body.source else [])},
          client_ip(request))
    _command(db, cam.id, "reload", p.user.id)
    db.commit()
    return _out(request, db, cam)


@router.delete("/{camera_id}", status_code=204)
def delete_camera(camera_id: str, request: Request, confirm: bool = Query(False), p: Principal = Depends(admin),
                  db: Session = Depends(get_db)) -> None:
    if not confirm:
        raise ApiError(400, "CONFIRMATION_REQUIRED", "Pass confirm=true to archive this camera.")
    cam = _get(db, camera_id)
    cam.archived_at, cam.enabled, cam.source_enc = utcnow(), False, None  # history preserved; secret wiped
    audit(db, p.user.id, "camera.archive", "camera", cam.id, {"name": cam.name}, client_ip(request))
    _command(db, cam.id, "reload", p.user.id)
    db.commit()


@router.post("/{camera_id}/actions", status_code=202)
def camera_action(camera_id: str, body: CameraAction, request: Request, p: Principal = Depends(operator),
                  db: Session = Depends(get_db)) -> dict:
    cam = _get(db, camera_id)
    if body.action == "disable" and p.user.role != "admin":
        raise ApiError(403, "FORBIDDEN", "Only administrators can disable cameras.")
    if body.action == "start":
        cam.enabled, cam.desired_state = True, "RUNNING"
    elif body.action == "pause":
        cam.desired_state = "PAUSED"
    elif body.action == "disable":
        cam.enabled = False
    _command(db, cam.id, body.action, p.user.id)
    audit(db, p.user.id, f"camera.{body.action}", "camera", cam.id, ip=client_ip(request))
    db.commit()
    return {"accepted": True, "note": "Command queued for the worker; status updates when the worker acts."}


@router.get("/{camera_id}/snapshot.jpg")
def snapshot(camera_id: str, request: Request, _: Principal = Depends(viewer), db: Session = Depends(get_db)):
    cam = _get(db, camera_id)
    path = request.app.state.settings.data_dir / "previews" / f"{cam.id}.jpg"
    st = db.get(m.CameraStatusRow, cam.id)
    if not path.is_file() or not st or not st.preview_timestamp:
        raise ApiError(404, "NO_SNAPSHOT", "No preview available for this camera.")
    age = (utcnow() - st.preview_timestamp).total_seconds()
    stale = age > request.app.state.settings.camera_stale_seconds
    return Response(path.read_bytes(), media_type="image/jpeg", headers={
        "Cache-Control": "no-store", "X-Frame-Captured-At": st.preview_timestamp.isoformat(),
        "X-Frame-Age-Seconds": f"{age:.1f}", "X-Preview-Stale": str(stale).lower(),
        "X-Camera-Status": st.connectivity, "X-Content-Type-Options": "nosniff"})


@router.get("/{camera_id}/health")
def camera_health(camera_id: str, request: Request, _: Principal = Depends(viewer), db: Session = Depends(get_db)) -> dict:
    cam = _get(db, camera_id)
    out = _out(request, db, cam)
    now = utcnow()
    st = db.get(m.CameraStatusRow, cam.id)
    return {"camera_id": cam.id, "status": out.status, "status_reason": out.statusReason,
            "frame_age_seconds": (now - st.last_frame_at).total_seconds() if st and st.last_frame_at else None,
            "inference_age_seconds": (now - st.last_inference_at).total_seconds() if st and st.last_inference_at else None,
            "capture_fps": out.captureFps, "inference_fps": out.inferenceFps,
            "inference_latency_ms": out.inferenceLatencyMs, "reconnect_count": out.reconnectCount,
            "last_error_code": out.lastErrorCode,
            "monitoring_unavailable": out.status in {"OFFLINE", "DISABLED", "PAUSED", "CONNECTING"}}


_ = timedelta
