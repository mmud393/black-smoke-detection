"""Incident lifecycle for one camera: open on VERIFIED, update/dedupe, clear after quiet period.

DB writes happen here (short transactions). Evidence files are written BEFORE the transaction that
creates the incident + email outbox rows, so a crash never leaves an incident without its evidence
(it may leave an orphan file, which retention cleans up)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from smoke_shared.db import models as m
from smoke_shared.db import utcnow
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

log = logging.getLogger("worker.incidents")


@dataclass
class OpenInfo:
    incident_id: str
    created: bool


class IncidentManager:
    def __init__(self, factory: sessionmaker, camera_id: str, clear_seconds: float, cooldown_seconds: float,
                 mono, model_id: str, model_revision: str, is_test: bool, alert_on_uncertain: bool = False) -> None:  # noqa: ANN001
        self.f, self.camera_id = factory, camera_id
        self.clear_seconds, self.cooldown = clear_seconds, cooldown_seconds
        self.mono, self.model_id, self.model_revision, self.is_test = mono, model_id, model_revision, is_test
        self.active_id: str | None = None
        self.last_verified_mono: float | None = None
        self.best_score = -1.0

    def reconcile_on_start(self) -> None:
        """Previously-active incidents are not silently resolved: mark tracking inactive and record the gap."""
        with self.f() as db:
            for inc in db.execute(select(m.Incident).where(m.Incident.camera_id == self.camera_id,
                                                          m.Incident.detection_active.is_(True))).scalars():
                inc.detection_active = False
                db.add(m.IncidentEvent(incident_id=inc.id, camera_id=self.camera_id, event_type="monitoring.gap",
                                       payload_json={"note": "worker restarted; software tracking interrupted, status unchanged"}))
            db.commit()

    def on_verified(self, *, score: float, darkness: float | None, reasons: list[str], captured_at: datetime,
                    evidence: list[dict] | None, recipients_snapshot: list[tuple[str, str]], dashboard_url: str,
                    camera_name: str, zone: str) -> OpenInfo | None:
        """Called on each VERIFIED tick. `evidence` is pre-written file metadata (or None to skip evidence this tick)."""
        self.last_verified_mono = self.mono()
        with self.f() as db:
            inc = db.get(m.Incident, self.active_id) if self.active_id else None
            if inc is None:
                # rearm: if a recent incident cleared < clear_seconds ago, reuse it instead of opening a new one
                recent = db.execute(select(m.Incident).where(m.Incident.camera_id == self.camera_id, m.Incident.status != "RESOLVED",
                                                             m.Incident.cleared_at.is_not(None)).order_by(m.Incident.cleared_at.desc())).scalars().first()
                if recent and (utcnow() - recent.cleared_at) < timedelta(seconds=self.clear_seconds):
                    inc = recent
                    inc.detection_active, inc.cleared_at = True, None
                    db.add(m.IncidentEvent(incident_id=inc.id, camera_id=self.camera_id, event_type="detection.resumed", payload_json={}))
            created = False
            if inc is None:
                created = True
                inc = m.Incident(camera_id=self.camera_id, first_seen_at=captured_at, last_seen_at=captured_at, verified_at=utcnow(),
                                 decision="VERIFIED_BY_RULES", is_test=self.is_test, model_id=self.model_id,
                                 model_revision=self.model_revision, best_score=score, darkness_score=darkness, reason_codes=reasons)
                db.add(inc)
                db.flush()
                db.add(m.IncidentEvent(incident_id=inc.id, camera_id=self.camera_id, event_type="incident.opened",
                                       payload_json={"reason_codes": reasons, "is_test": self.is_test, "modelScore": score}))
                self._enqueue(db, inc, recipients_snapshot, dashboard_url, camera_name, zone)
            inc.last_seen_at = captured_at
            self.active_id = inc.id
            if score > (inc.best_score or -1) or created:
                inc.best_score, inc.darkness_score, inc.reason_codes = max(score, inc.best_score or 0), darkness, reasons
                better = True
            else:
                better = False
            if evidence and (created or better):
                for ev in evidence:
                    db.add(m.Evidence(incident_id=inc.id, **ev))
                if not created:
                    db.add(m.IncidentEvent(incident_id=inc.id, camera_id=self.camera_id, event_type="evidence.improved", payload_json={"modelScore": score}))
            db.commit()
            self.best_score = inc.best_score or score
            return OpenInfo(inc.id, created)

    def _enqueue(self, db, inc: m.Incident, recipients: list[tuple[str, str]], dashboard_url: str, cam: str, zone: str) -> None:  # noqa: ANN001
        """Same transaction as the incident. Cooldown suppresses extra emails for the same camera."""
        since = utcnow() - timedelta(seconds=self.cooldown)
        prior = db.execute(select(m.NotificationOutbox.id).join(m.Incident, m.Incident.id == m.NotificationOutbox.incident_id)
                           .where(m.Incident.camera_id == self.camera_id, m.NotificationOutbox.category == "incident",
                                  m.NotificationOutbox.created_at > since, m.NotificationOutbox.incident_id != inc.id)).first()
        if prior:
            db.add(m.IncidentEvent(incident_id=inc.id, camera_id=self.camera_id, event_type="alert.suppressed_cooldown",
                                   payload_json={"cooldown_seconds": self.cooldown}))
            return
        for rid, email in recipients:
            db.add(m.NotificationOutbox(incident_id=inc.id, category="incident", idempotency_key=f"incident:{inc.id}:open:{rid}",
                                        recipient=email, payload_json={"camera": cam, "zone": zone, "dashboard_url": dashboard_url,
                                                                      "is_test": inc.is_test}))
        db.add(m.IncidentEvent(incident_id=inc.id, camera_id=self.camera_id, event_type="alert.queued", payload_json={"recipients": len(recipients)}))

    def on_tick_no_verified(self) -> bool:
        """Clear tracking after clear_seconds of no verified smoke. Returns True if cleared now."""
        if not self.active_id or self.last_verified_mono is None:
            return False
        if self.mono() - self.last_verified_mono < self.clear_seconds:
            return False
        with self.f() as db:
            inc = db.get(m.Incident, self.active_id)
            if inc and inc.detection_active:
                inc.detection_active, inc.cleared_at = False, utcnow()
                db.add(m.IncidentEvent(incident_id=inc.id, camera_id=self.camera_id, event_type="detection.cleared",
                                       payload_json={"clear_seconds": self.clear_seconds}))
                db.commit()
        self.active_id = None
        return True
