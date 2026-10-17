from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import Principal, admin, client_ip, get_box, viewer
from ..services import settings_store as ss
from ..services.audit import audit

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


class SettingsPatch(BaseModel):
    smtp_host: str | None = Field(None, max_length=253)
    smtp_port: int | None = Field(None, ge=1, le=65535)
    smtp_tls_mode: str | None = Field(None, pattern="^(starttls|ssl)$")
    smtp_username: str | None = Field(None, max_length=254)
    smtp_from: str | None = Field(None, max_length=254)
    smtp_timeout_seconds: int | None = Field(None, ge=1, le=120)
    smtp_max_attempts: int | None = Field(None, ge=1, le=20)
    smtp_delivery_enabled: bool | None = None
    # secret semantics: omitted = unchanged; string = replace; clear_smtp_password=true removes
    smtp_password: str | None = Field(None, max_length=256)
    clear_smtp_password: bool = False
    factory_name: str | None = Field(None, max_length=100)
    factory_timezone: str | None = None
    alert_cooldown_seconds: int | None = Field(None, ge=0, le=86400)
    evidence_retention_days: int | None = Field(None, ge=1, le=3650)
    evidence_max_gb: float | None = Field(None, gt=0)
    alert_on_camera_offline: bool | None = None
    alert_repeat_minutes: int | None = Field(None, ge=0, le=1440)


@router.get("")
def get_settings(request: Request, _: Principal = Depends(viewer), db: Session = Depends(get_db)) -> dict:
    return ss.effective(db, request.app.state.settings)


@router.patch("")
def patch_settings(body: SettingsPatch, request: Request, p: Principal = Depends(admin), db: Session = Depends(get_db)) -> dict:
    data = body.model_dump(exclude_unset=True, exclude={"smtp_password", "clear_smtp_password"})
    if "factory_timezone" in data and data["factory_timezone"]:
        from zoneinfo import ZoneInfo
        try:
            ZoneInfo(data["factory_timezone"])
        except Exception:  # noqa: BLE001
            from ..errors import ApiError
            raise ApiError(422, "VALIDATION_ERROR", "Unknown timezone.") from None
    for k, v in data.items():
        ss.put(db, k, v)
    changed = sorted(data)
    if body.clear_smtp_password:
        ss.clear(db, "smtp_password")
        changed.append("smtp_password:cleared")
    elif body.smtp_password:
        ss.put_secret(db, get_box(request), "smtp_password", body.smtp_password)
        changed.append("smtp_password:set")
    audit(db, p.user.id, "settings.update", "settings", None, {"changed": changed}, client_ip(request))
    db.commit()
    return ss.effective(db, request.app.state.settings)
