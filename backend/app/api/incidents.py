from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from smoke_shared.db import models as m
from smoke_shared.db import utcnow
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import Principal, client_ip, operator, viewer
from ..errors import ApiError
from ..services.audit import audit, event

router = APIRouter(prefix="/api/v1", tags=["incidents"])


class ResolveIn(BaseModel):
    outcome: str = Field(pattern="^(TRUE_SMOKE|FALSE_ALARM|UNKNOWN)$")
    note: str = Field("", max_length=2000)


class NoteIn(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


def _dto(db: Session, i: m.Incident) -> dict:
    cam = db.get(m.Camera, i.camera_id)
    thumb = db.execute(select(m.Evidence.id).where(m.Evidence.incident_id == i.id, m.Evidence.type == "annotated",
                                                   m.Evidence.deleted_at.is_(None)).order_by(m.Evidence.captured_at.desc())).first()
    mail = db.execute(select(m.NotificationOutbox.state).where(m.NotificationOutbox.incident_id == i.id,
                                                              m.NotificationOutbox.category == "incident")).scalars().all()
    delivery = "NONE"
    for s in ("FAILED", "RETRY", "PENDING", "SENDING", "ACCEPTED_BY_SMTP"):
        if s in mail:
            delivery = s
            break
    return {
        "id": i.id, "camera_id": i.camera_id, "camera_name": cam.name if cam else None, "zone": cam.zone if cam else None,
        "status": i.status, "outcome": i.outcome, "decision": i.decision, "detection_active": i.detection_active,
        "is_test": i.is_test, "first_seen_at": i.first_seen_at.isoformat(), "last_seen_at": i.last_seen_at.isoformat(),
        "verified_at": i.verified_at.isoformat() if i.verified_at else None,
        "acknowledged_at": i.acknowledged_at.isoformat() if i.acknowledged_at else None,
        "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
        "modelScore": i.best_score, "darknessScore": i.darkness_score, "decisionReasons": i.reason_codes or [],
        "model_id": i.model_id, "model_revision": i.model_revision, "notes": i.notes,
        "thumbnail_evidence_id": thumb[0] if thumb else None, "delivery_state": delivery,
        "disclaimer": "Software-detected suspected black smoke; verify with site procedures.",
    }


def _get(db: Session, iid: str) -> m.Incident:
    i = db.get(m.Incident, iid)
    if not i:
        raise ApiError(404, "NOT_FOUND", "Incident not found.")
    return i


@router.get("/incidents")
def list_incidents(camera_id: str | None = None, status: str | None = None, from_: datetime | None = Query(None, alias="from"),
                   to: datetime | None = None, include_test: bool = True, limit: int = Query(25, ge=1, le=100),
                   offset: int = Query(0, ge=0), _: Principal = Depends(viewer), db: Session = Depends(get_db)) -> dict:
    q = select(m.Incident)
    if camera_id:
        q = q.where(m.Incident.camera_id == camera_id)
    if status:
        q = q.where(m.Incident.status == status)
    if from_:
        q = q.where(m.Incident.first_seen_at >= from_)
    if to:
        q = q.where(m.Incident.first_seen_at <= to)
    if not include_test:
        q = q.where(m.Incident.is_test.is_(False))
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(q.order_by(m.Incident.first_seen_at.desc()).limit(limit).offset(offset)).scalars().all()
    return {"items": [_dto(db, i) for i in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/incidents/export.csv")
def export_csv(from_: datetime = Query(..., alias="from"), to: datetime = Query(...), _: Principal = Depends(viewer),
               db: Session = Depends(get_db)) -> Response:
    if to <= from_ or to - from_ > timedelta(days=366):
        raise ApiError(422, "VALIDATION_ERROR", "Date range must be positive and at most 366 days.")
    rows = db.execute(select(m.Incident).where(m.Incident.first_seen_at >= from_, m.Incident.first_seen_at <= to)
                      .order_by(m.Incident.first_seen_at).limit(10000)).scalars().all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "camera_id", "first_seen_utc", "status", "outcome", "decision", "is_test", "model_score", "darkness_score", "reasons"])
    for i in rows:
        # prefix risky cells to avoid spreadsheet formula injection
        w.writerow([i.id, i.camera_id, i.first_seen_at.isoformat(), i.status, i.outcome or "", i.decision, i.is_test,
                    i.best_score, i.darkness_score, ";".join(i.reason_codes or [])])
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=incidents.csv"})


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str, _: Principal = Depends(viewer), db: Session = Depends(get_db)) -> dict:
    i = _get(db, incident_id)
    events = db.execute(select(m.IncidentEvent).where(m.IncidentEvent.incident_id == i.id).order_by(m.IncidentEvent.id)).scalars()
    return {**_dto(db, i), "timeline": [{"id": e.id, "type": e.event_type, "at": e.created_at.isoformat(),
                                         "actor": e.actor_user_id, "payload": e.payload_json} for e in events]}


@router.post("/incidents/{incident_id}/acknowledge")
def acknowledge(incident_id: str, request: Request, p: Principal = Depends(operator), db: Session = Depends(get_db)) -> dict:
    i = _get(db, incident_id)
    if i.status != "OPEN":
        raise ApiError(409, "INVALID_TRANSITION", f"Cannot acknowledge an incident that is {i.status}.")
    i.status, i.acknowledged_by, i.acknowledged_at = "ACKNOWLEDGED", p.user.id, utcnow()
    event(db, "incident.acknowledged", incident_id=i.id, camera_id=i.camera_id, actor=p.user.id)
    audit(db, p.user.id, "incident.acknowledge", "incident", i.id, ip=client_ip(request))
    db.commit()
    return _dto(db, i)


@router.post("/incidents/{incident_id}/resolve")
def resolve(incident_id: str, body: ResolveIn, request: Request, p: Principal = Depends(operator),
            db: Session = Depends(get_db)) -> dict:
    i = _get(db, incident_id)
    if i.status == "RESOLVED":
        raise ApiError(409, "INVALID_TRANSITION", "Incident is already resolved.")
    i.status, i.outcome, i.resolved_by, i.resolved_at = "RESOLVED", body.outcome, p.user.id, utcnow()
    if body.note:
        i.notes = (i.notes + f"\n[{utcnow().isoformat()}] {p.user.username}: {body.note}").strip()
    event(db, "incident.resolved", incident_id=i.id, camera_id=i.camera_id, actor=p.user.id, payload={"outcome": body.outcome})
    audit(db, p.user.id, "incident.resolve", "incident", i.id, {"outcome": body.outcome}, client_ip(request))
    db.commit()
    return _dto(db, i)


@router.post("/incidents/{incident_id}/notes")
def add_note(incident_id: str, body: NoteIn, p: Principal = Depends(operator), db: Session = Depends(get_db)) -> dict:
    i = _get(db, incident_id)
    i.notes = (i.notes + f"\n[{utcnow().isoformat()}] {p.user.username}: {body.note}").strip()
    event(db, "incident.note", incident_id=i.id, camera_id=i.camera_id, actor=p.user.id)
    db.commit()
    return _dto(db, i)


@router.get("/incidents/{incident_id}/evidence")
def evidence_list(incident_id: str, _: Principal = Depends(viewer), db: Session = Depends(get_db)) -> list[dict]:
    _get(db, incident_id)
    rows = db.execute(select(m.Evidence).where(m.Evidence.incident_id == incident_id, m.Evidence.deleted_at.is_(None))
                      .order_by(m.Evidence.captured_at)).scalars()
    return [{"id": e.id, "type": e.type, "sha256": e.sha256, "width": e.width, "height": e.height, "bytes": e.bytes,
             "captured_at": e.captured_at.isoformat(), "retention_pin": e.retention_pin, "meta": e.meta,
             "url": f"/api/v1/evidence/{e.id}/image"} for e in rows]


@router.get("/evidence/{evidence_id}/image")
def evidence_image(evidence_id: str, request: Request, _: Principal = Depends(viewer), db: Session = Depends(get_db)) -> Response:
    ev = db.get(m.Evidence, evidence_id)
    if not ev or ev.deleted_at:
        raise ApiError(404, "NOT_FOUND", "Evidence not found.")
    root = (request.app.state.settings.data_dir / "evidence").resolve()
    path = (root / ev.relative_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():  # traversal / missing file guard
        raise ApiError(404, "NOT_FOUND", "Evidence file unavailable.")
    return Response(path.read_bytes(), media_type="image/jpeg", headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'inline; filename="{ev.id}.jpg"'})
