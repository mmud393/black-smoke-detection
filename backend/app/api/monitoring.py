from __future__ import annotations

import asyncio
import json
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse
from smoke_shared.db import models as m
from smoke_shared.db import utcnow
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import Principal, viewer
from ..services.health_service import system_health

router = APIRouter(prefix="/api/v1", tags=["monitoring"])


@router.get("/monitoring/summary")
def summary(request: Request, _: Principal = Depends(viewer), db: Session = Depends(get_db)) -> dict:
    now = utcnow()
    cams = db.execute(select(m.Camera).where(m.Camera.archived_at.is_(None))).scalars().all()
    st = {s.camera_id: s for s in db.execute(select(m.CameraStatusRow)).scalars()}
    stale = request.app.state.settings.camera_stale_seconds * 3
    enabled = [c for c in cams if c.enabled]

    def online(c: m.Camera) -> bool:
        s = st.get(c.id)
        return bool(s and s.connectivity == "ONLINE" and s.worker_heartbeat_at and (now - s.worker_heartbeat_at).total_seconds() < stale)

    day = now - timedelta(hours=24)
    inc24 = db.execute(select(m.Incident).where(m.Incident.first_seen_at >= day)).scalars().all()
    trend: dict[str, int] = {}
    for i in inc24:
        k = i.first_seen_at.replace(minute=0, second=0, microsecond=0).isoformat()
        trend[k] = trend.get(k, 0) + 1
    last_inf = db.execute(select(func.max(m.CameraStatusRow.last_inference_at))).scalar_one()
    return {
        "cameras_total": len(cams), "cameras_enabled": len(enabled), "cameras_online": sum(online(c) for c in enabled),
        "cameras_offline": sum(not online(c) for c in enabled),
        "incidents_today": sum(1 for i in inc24 if i.first_seen_at.date() == now.date()),
        "active_incidents": db.execute(select(func.count()).select_from(m.Incident).where(m.Incident.detection_active.is_(True), m.Incident.status != "RESOLVED")).scalar_one(),
        "unacknowledged_incidents": db.execute(select(func.count()).select_from(m.Incident).where(m.Incident.status == "OPEN")).scalar_one(),
        "failed_emails": db.execute(select(func.count()).select_from(m.NotificationOutbox).where(m.NotificationOutbox.state == "FAILED")).scalar_one(),
        "last_inference_age_seconds": (now - last_inf).total_seconds() if last_inf else None,
        "incident_trend_24h": [{"hour": k, "count": v} for k, v in sorted(trend.items())],
        "monitoring_unavailable": bool(enabled) and not any(online(c) for c in enabled),
    }


@router.get("/monitoring/events")
async def events(request: Request, last_event_id: str | None = Header(None), _: Principal = Depends(viewer)):
    factory = request.app.state.session_factory
    try:
        cursor = int(last_event_id) if last_event_id else None
    except ValueError:
        cursor = None

    def _poll(after: int | None) -> tuple[list[tuple[int, str, dict]], int]:
        with factory() as db:
            if after is None:  # new client: start at head, no history replay
                return [], db.execute(select(func.coalesce(func.max(m.IncidentEvent.id), 0))).scalar_one()
            rows = db.execute(select(m.IncidentEvent).where(m.IncidentEvent.id > after).order_by(m.IncidentEvent.id).limit(200)).scalars().all()
            return [(r.id, r.event_type, {"incident_id": r.incident_id, "camera_id": r.camera_id, **(r.payload_json or {})}) for r in rows], (rows[-1].id if rows else after)

    async def gen():
        nonlocal cursor
        _, cursor = await asyncio.to_thread(_poll, cursor) if cursor is None else (None, cursor)
        yield "retry: 3000\n\n"
        idle = 0
        while not await request.is_disconnected():
            rows, cursor = await asyncio.to_thread(_poll, cursor)
            for eid, etype, payload in rows:
                yield f"id: {eid}\nevent: {etype}\ndata: {json.dumps(payload)}\n\n"
            idle = 0 if rows else idle + 1
            if idle and idle % 10 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.get("/system/health")
def detailed_health(request: Request, _: Principal = Depends(viewer), db: Session = Depends(get_db)) -> dict:
    return system_health(db, request.app.state.settings, detailed=True)
