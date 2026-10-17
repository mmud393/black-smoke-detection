from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, EmailStr
from smoke_shared.db import models as m
from smoke_shared.db import utcnow
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import Principal, admin, client_ip, viewer
from ..errors import ApiError
from ..services.audit import audit

router = APIRouter(prefix="/api/v1", tags=["alerts"])


class RecipientIn(BaseModel):
    name: str
    email: EmailStr
    enabled: bool = True
    categories: list[str] = ["incident", "test"]


def _n(o: m.NotificationOutbox) -> dict:
    return {"id": o.id, "incident_id": o.incident_id, "category": o.category, "recipient": o.recipient, "state": o.state,
            "attempts": o.attempts, "next_attempt_at": o.next_attempt_at.isoformat(), "last_error": o.last_error_redacted,
            "smtp_response": o.smtp_response, "created_at": o.created_at.isoformat(),
            "sent_at": o.sent_at.isoformat() if o.sent_at else None,
            "note": "ACCEPTED_BY_SMTP means the mail server accepted the message, not that it reached an inbox."}


@router.get("/alerts")
def list_alerts(state: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                _: Principal = Depends(viewer), db: Session = Depends(get_db)) -> dict:
    q = select(m.NotificationOutbox).order_by(m.NotificationOutbox.created_at.desc())
    if state:
        q = q.where(m.NotificationOutbox.state == state)
    rows = db.execute(q.limit(limit).offset(offset)).scalars().all()
    return {"items": [_n(o) for o in rows]}


@router.post("/alerts/test", status_code=202)
def test_alert(request: Request, p: Principal = Depends(admin), db: Session = Depends(get_db)) -> dict:
    recips = db.execute(select(m.NotificationRecipient).where(m.NotificationRecipient.enabled.is_(True))).scalars().all()
    recips = [r for r in recips if "test" in (r.categories or [])]
    if not recips:
        raise ApiError(409, "NO_RECIPIENTS", "No enabled recipients subscribed to test messages.")
    recent = db.execute(select(m.NotificationOutbox).where(m.NotificationOutbox.category == "test",
                                                           m.NotificationOutbox.created_at > utcnow().replace(microsecond=0)
                                                           - __import__("datetime").timedelta(seconds=30))).first()
    if recent:
        raise ApiError(429, "RATE_LIMITED", "A test email was queued in the last 30 seconds.")
    stamp = utcnow().isoformat()
    for r in recips:
        db.add(m.NotificationOutbox(category="test", idempotency_key=f"test:{r.id}:{stamp}", recipient=r.email,
                                    payload_json={"kind": "test"}))
    audit(db, p.user.id, "alerts.test", ip=client_ip(request))
    db.commit()
    return {"queued": len(recips)}


@router.post("/alerts/{notification_id}/retry")
def retry(notification_id: str, p: Principal = Depends(admin), db: Session = Depends(get_db)) -> dict:
    o = db.get(m.NotificationOutbox, notification_id)
    if not o:
        raise ApiError(404, "NOT_FOUND", "Notification not found.")
    if o.state == "ACCEPTED_BY_SMTP":
        return _n(o)  # idempotent: nothing to retry
    if o.state in {"FAILED", "RETRY"}:
        o.state, o.next_attempt_at, o.lease_owner = "PENDING", utcnow(), None
        audit(db, p.user.id, "alerts.retry", "notification", o.id)
        db.commit()
    return _n(o)


@router.get("/recipients")
def recipients(_: Principal = Depends(admin), db: Session = Depends(get_db)) -> list[dict]:
    return [{"id": r.id, "name": r.name, "email": r.email, "enabled": r.enabled, "categories": r.categories}
            for r in db.execute(select(m.NotificationRecipient).order_by(m.NotificationRecipient.name)).scalars()]


@router.post("/recipients", status_code=201)
def add_recipient(body: RecipientIn, request: Request, p: Principal = Depends(admin), db: Session = Depends(get_db)) -> dict:
    if db.execute(select(m.NotificationRecipient).where(m.NotificationRecipient.email == body.email)).first():
        raise ApiError(409, "CONFLICT", "Recipient already exists.")
    r = m.NotificationRecipient(name=body.name, email=str(body.email), enabled=body.enabled, categories=body.categories)
    db.add(r)
    audit(db, p.user.id, "recipient.add", "recipient", r.id, {"email": r.email}, client_ip(request))
    db.commit()
    return {"id": r.id}


@router.delete("/recipients/{rid}", status_code=204)
def del_recipient(rid: str, p: Principal = Depends(admin), db: Session = Depends(get_db)) -> None:
    r = db.get(m.NotificationRecipient, rid)
    if r:
        db.delete(r)
        audit(db, p.user.id, "recipient.delete", "recipient", rid)
        db.commit()
