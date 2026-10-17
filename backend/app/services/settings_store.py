"""Typed app settings. Secrets stored as {"enc": fernet}; API never returns them."""

from __future__ import annotations

from smoke_shared.config import Settings
from smoke_shared.crypto import SecretBox
from smoke_shared.db import models as m
from sqlalchemy.orm import Session

SMTP_KEYS = ["smtp_host", "smtp_port", "smtp_tls_mode", "smtp_username", "smtp_from", "smtp_timeout_seconds",
             "smtp_max_attempts", "smtp_delivery_enabled"]
SITE_KEYS = ["factory_name", "factory_timezone", "alert_cooldown_seconds", "evidence_retention_days",
             "evidence_max_gb", "alert_on_camera_offline", "alert_repeat_minutes"]
SECRET_KEYS = ["smtp_password"]


def get_value(db: Session, key: str, default=None):  # noqa: ANN001, ANN201
    row = db.get(m.AppSetting, key)
    return row.value_json if row and not row.is_secret else default


def get_secret(db: Session, box: SecretBox | None, key: str) -> str | None:
    row = db.get(m.AppSetting, key)
    if not row or not row.is_secret or not box or not row.value_json:
        return None
    return box.decrypt(row.value_json["enc"])


def put(db: Session, key: str, value) -> None:  # noqa: ANN001
    row = db.get(m.AppSetting, key)
    if row:
        row.value_json, row.is_secret = value, False
    else:
        db.add(m.AppSetting(key=key, value_json=value, is_secret=False))


def put_secret(db: Session, box: SecretBox, key: str, plaintext: str) -> None:
    val = {"enc": box.encrypt(plaintext)}
    row = db.get(m.AppSetting, key)
    if row:
        row.value_json, row.is_secret = val, True
    else:
        db.add(m.AppSetting(key=key, value_json=val, is_secret=True))


def clear(db: Session, key: str) -> None:
    row = db.get(m.AppSetting, key)
    if row:
        db.delete(row)


def effective(db: Session, env: Settings) -> dict:
    out = {k: get_value(db, k, getattr(env, k, None)) for k in SMTP_KEYS + SITE_KEYS}
    out["smtp_password_configured"] = bool(db.get(m.AppSetting, "smtp_password")) or bool(env.smtp_password)
    return out
