"""SQLAlchemy models shared by API and worker. Timestamps are UTC-aware.

Credential columns (`*_enc`) hold Fernet ciphertext only."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .session import utcnow


class UTCDateTime(TypeDecorator):
    """Stores naive UTC in SQLite, returns tz-aware UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ANN001
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime rejected; use UTC-aware values")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):  # noqa: ANN001
        return value.replace(tzinfo=UTC) if value else None


class Base(DeclarativeBase):
    pass


def _id() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class DetectionProfile(Base, TimestampMixin):
    __tablename__ = "detection_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    model_backend: Mapped[str] = mapped_column(String(32), default="grounding_dino")
    text_prompts: Mapped[list] = mapped_column(JSON, default=list)
    candidate_score_min: Mapped[float] = mapped_column(Float, default=0.30)
    darkness_l_max: Mapped[float] = mapped_column(Float, default=45.0)  # LAB L* (0-100) median upper bound
    darkness_contrast_min: Mapped[float] = mapped_column(Float, default=12.0)  # L* below local background
    min_detection_count: Mapped[int] = mapped_column(Integer, default=3)
    min_seconds: Mapped[float] = mapped_column(Float, default=3.0)
    clear_seconds: Mapped[float] = mapped_column(Float, default=20.0)
    min_box_area_frac: Mapped[float] = mapped_column(Float, default=0.002)
    max_box_area_frac: Mapped[float] = mapped_column(Float, default=0.60)
    alert_on_uncertain: Mapped[bool] = mapped_column(Boolean, default=False)


class Camera(Base, TimestampMixin):
    __tablename__ = "cameras"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(100))
    zone: Mapped[str] = mapped_column(String(100), default="")
    location_description: Mapped[str] = mapped_column(String(300), default="")
    source_kind: Mapped[str] = mapped_column(String(16), default="RTSP")
    source_enc: Mapped[str | None] = mapped_column(Text)  # encrypted RTSP URL / file path
    sanitized_endpoint: Mapped[str] = mapped_column(String(300), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    desired_state: Mapped[str] = mapped_column(String(16), default="RUNNING")
    transport: Mapped[str] = mapped_column(String(8), default="tcp")
    capture_fps_limit: Mapped[float] = mapped_column(Float, default=5.0)
    inference_fps_target: Mapped[float] = mapped_column(Float, default=1.0)
    preview_fps: Mapped[float] = mapped_column(Float, default=1.0)
    max_width: Mapped[int] = mapped_column(Integer, default=1280)
    roi_polygons: Mapped[list] = mapped_column(JSON, default=list)  # normalized [[x,y],...]
    ignore_polygons: Mapped[list] = mapped_column(JSON, default=list)
    detection_profile_id: Mapped[str | None] = mapped_column(ForeignKey("detection_profiles.id"))
    timezone: Mapped[str | None] = mapped_column(String(64))
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime)  # soft delete keeps history
    status: Mapped[CameraStatusRow] = relationship(back_populates="camera", uselist=False)


class CameraStatusRow(Base):
    __tablename__ = "camera_status"
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"), primary_key=True)  # one row per camera
    connectivity: Mapped[str] = mapped_column(String(16), default="DISABLED")
    last_transition_reason: Mapped[str | None] = mapped_column(String(200))
    last_transition_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_frame_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_inference_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    capture_fps: Mapped[float | None] = mapped_column(Float)
    inference_fps: Mapped[float | None] = mapped_column(Float)
    preview_timestamp: Mapped[datetime | None] = mapped_column(UTCDateTime)
    inference_latency_ms: Mapped[float | None] = mapped_column(Float)
    reconnect_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    frame_width: Mapped[int | None] = mapped_column(Integer)
    frame_height: Mapped[int | None] = mapped_column(Integer)
    worker_heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    camera: Mapped[Camera] = relationship(back_populates="status")


class Incident(Base, TimestampMixin):
    __tablename__ = "incidents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"))
    status: Mapped[str] = mapped_column(String(16), default="OPEN")  # operator workflow
    outcome: Mapped[str | None] = mapped_column(String(16))
    detection_active: Mapped[bool] = mapped_column(Boolean, default=True)  # software tracking, not human ack
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    cleared_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    acknowledged_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    resolved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    decision: Mapped[str] = mapped_column(String(24), default="VERIFIED_BY_RULES")
    is_test: Mapped[bool] = mapped_column(Boolean, default=False)  # simulated TEST MODE incident
    model_id: Mapped[str | None] = mapped_column(String(200))
    model_revision: Mapped[str | None] = mapped_column(String(64))
    best_score: Mapped[float | None] = mapped_column(Float)  # model score, NOT a probability
    darkness_score: Mapped[float | None] = mapped_column(Float)
    reason_codes: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (
        Index("ix_incidents_camera_status", "camera_id", "status"),
        Index("ix_incidents_first_seen", "first_seen_at"),
    )


class IncidentEvent(Base):
    """Immutable timeline + SSE source. Integer PK is monotonic (AUTOINCREMENT semantics)."""

    __tablename__ = "incident_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id"), index=True)
    camera_id: Mapped[str | None] = mapped_column(ForeignKey("cameras.id"))
    event_type: Mapped[str] = mapped_column(String(48))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    __table_args__ = {"sqlite_autoincrement": True}


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    type: Mapped[str] = mapped_column(String(16))
    relative_path: Mapped[str] = mapped_column(String(200))  # relative to DATA_DIR/evidence, validated
    sha256: Mapped[str] = mapped_column(String(64))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    bytes: Mapped[int] = mapped_column(Integer)
    captured_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    retention_pin: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class NotificationRecipient(Base):
    __tablename__ = "notification_recipients"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    categories: Mapped[list] = mapped_column(JSON, default=lambda: ["incident", "test"])
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id"))
    category: Mapped[str] = mapped_column(String(24))
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    recipient: Mapped[str] = mapped_column(String(254))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    attachment_evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    state: Mapped[str] = mapped_column(String(20), default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    lease_owner: Mapped[str | None] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error_redacted: Mapped[str | None] = mapped_column(String(500))
    smtp_response: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    __table_args__ = (Index("ix_outbox_state_due", "state", "next_attempt_at"),)


class WorkerCommand(Base):
    __tablename__ = "worker_commands"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    target: Mapped[str] = mapped_column(String(64))  # camera id or "worker"
    command: Mapped[str] = mapped_column(String(32))
    args: Mapped[dict] = mapped_column(JSON, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    error: Mapped[str | None] = mapped_column(String(300))
    requested_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    __table_args__ = (Index("ix_commands_pending", "status", "id"), {"sqlite_autoincrement": True})


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    worker_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    heartbeat_at: Mapped[datetime] = mapped_column(UTCDateTime)
    version: Mapped[str] = mapped_column(String(32), default="")
    info: Mapped[dict] = mapped_column(JSON, default=dict)  # nonsecret telemetry: cpu, ram, model state


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)  # if True, value is {"enc": "<fernet>"}
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    source_ip: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    __table_args__ = {"sqlite_autoincrement": True}


_ = (UniqueConstraint, event, relationship)  # re-exported for migrations convenience
__all__ = [n for n, v in list(globals().items()) if isinstance(v, type) and issubclass(v, Base) and v is not Base] + ["Base", "UTCDateTime"]
