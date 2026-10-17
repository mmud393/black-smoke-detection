from __future__ import annotations

import shutil

from smoke_shared.config import Settings
from smoke_shared.db import models as m
from smoke_shared.db import utcnow
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

HEARTBEAT_STALE_S = 30


def system_health(db: Session, settings: Settings, detailed: bool = False) -> dict:
    now = utcnow()
    comps: dict[str, dict] = {"api": {"state": "OK"}}
    try:
        db.execute(text("SELECT 1"))
        comps["database"] = {"state": "OK"}
    except Exception:  # noqa: BLE001
        comps["database"] = {"state": "DEGRADED", "detail": "database query failed"}
    hb = db.execute(select(m.WorkerHeartbeat).order_by(m.WorkerHeartbeat.heartbeat_at.desc())).scalars().first()
    if not hb:
        comps["worker"] = {"state": "UNKNOWN", "detail": "no worker heartbeat has ever been recorded"}
        comps["model"] = {"state": "UNKNOWN", "detail": "worker not reporting"}
    else:
        age = (now - hb.heartbeat_at).total_seconds()
        comps["worker"] = {"state": "OK" if age < HEARTBEAT_STALE_S else "DEGRADED", "heartbeat_age_seconds": round(age, 1),
                           "detail": None if age < HEARTBEAT_STALE_S else "worker heartbeat is stale"}
        info = hb.info or {}
        mstate = info.get("model_state", "UNKNOWN")
        comps["model"] = {"state": "OK" if mstate == "READY" and age < HEARTBEAT_STALE_S else "DEGRADED" if mstate != "UNKNOWN" else "UNKNOWN",
                          "model_state": mstate, "model_id": info.get("model_id"), "revision": info.get("model_revision"),
                          "device": info.get("device"), "detail": info.get("model_error")}
    pending = db.execute(select(func.count()).select_from(m.NotificationOutbox).where(m.NotificationOutbox.state.in_(["PENDING", "RETRY", "SENDING"]))).scalar_one()
    failed = db.execute(select(func.count()).select_from(m.NotificationOutbox).where(m.NotificationOutbox.state == "FAILED")).scalar_one()
    comps["email"] = {"state": "DEGRADED" if failed else "OK", "queued": pending, "failed": failed,
                      "delivery_enabled": bool((db.get(m.AppSetting, "smtp_delivery_enabled") or m.AppSetting(value_json=settings.smtp_delivery_enabled)).value_json)}
    try:
        du = shutil.disk_usage(settings.data_dir)
        free_gb = du.free / 1e9
        comps["storage"] = {"state": "OK" if free_gb > 2 else "DEGRADED", "free_gb": round(free_gb, 1)}
    except OSError:
        comps["storage"] = {"state": "DEGRADED", "detail": "data dir unavailable"}
    overall = "READY" if all(c["state"] == "OK" for c in comps.values()) else "DEGRADED"
    if comps["database"]["state"] != "OK":
        overall = "NOT_READY"
    out = {"status": overall, "components": comps, "time": now.isoformat()}
    if detailed and hb:
        out["worker_info"] = hb.info
    return out
