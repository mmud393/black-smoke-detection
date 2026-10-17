from __future__ import annotations

from smoke_shared.db import models as m
from smoke_shared.redaction import redact
from sqlalchemy.orm import Session


def audit(db: Session, actor: str | None, action: str, entity_type: str | None = None,
          entity_id: str | None = None, meta: dict | None = None, ip: str | None = None) -> None:
    """Adds an audit row to the caller's transaction (caller commits). Metadata is redacted."""
    db.add(m.AuditLog(actor_user_id=actor, action=action, entity_type=entity_type, entity_id=entity_id,
                      meta=redact(meta or {}), source_ip=ip))


def event(db: Session, event_type: str, *, incident_id: str | None = None, camera_id: str | None = None,
          payload: dict | None = None, actor: str | None = None) -> None:
    db.add(m.IncidentEvent(incident_id=incident_id, camera_id=camera_id, event_type=event_type,
                           payload_json=redact(payload or {}), actor_user_id=actor))
