from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.health_service import system_health

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict:
    """API process liveness only. Says nothing about worker, model or cameras."""
    from datetime import UTC, datetime
    return {"status": "alive", "time": datetime.now(UTC).isoformat()}


@router.get("/health/ready")
def ready(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    """DB + worker heartbeat + model state. DEGRADED (HTTP 200) when worker/model are unavailable;
    NOT_READY (503) only when the database itself is unusable."""
    h = system_health(db, request.app.state.settings)
    if h["status"] == "NOT_READY":
        response.status_code = 503
    return {"status": h["status"], "components": {k: v["state"] for k, v in h["components"].items()}}
