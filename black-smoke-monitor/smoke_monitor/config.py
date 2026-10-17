"""Parse and validate .env configuration. Errors never include secret values."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import dotenv_values

PLACEHOLDER_MARKERS = ("replace_with", "recipient@example.com")


class ConfigError(Exception):
    """Raised for missing/invalid configuration; message is safe to print."""


@dataclass(frozen=True)
class Config:
    camera_name: str
    camera_ip: str
    camera_port: int
    camera_username: str
    camera_password: str
    camera_channel: int
    camera_subtype: int
    camera_rtsp_url: str
    rtsp_transport: str
    connect_timeout: float
    stall_timeout: float

    model_id: str
    model_local_dir: Path
    device: str
    inference_fps: float
    box_threshold: float
    text_threshold: float
    detection_prompt: str
    dark_luminance: int
    min_dark_fraction: float
    min_motion_fraction: float
    min_detections: int
    min_span_seconds: float
    clear_seconds: float
    max_frame_age: float

    smtp_host: str
    smtp_port: int
    smtp_security: str
    smtp_username: str
    smtp_password: str
    smtp_from: str
    alert_to: tuple[str, ...]
    smtp_timeout: float
    email_retry_limit: int

    timezone: ZoneInfo
    data_dir: Path
    keep_days: int
    log_level: str

    @property
    def rtsp_url(self) -> str:
        """Full RTSP URL (contains credentials: never log it, use redacted_url)."""
        return build_rtsp_url(
            self.camera_ip, self.camera_port, self.camera_username, self.camera_password,
            self.camera_channel, self.camera_subtype, self.camera_rtsp_url,
        )

    @property
    def redacted_url(self) -> str:
        return build_rtsp_url(
            self.camera_ip, self.camera_port, "***", "***",
            self.camera_channel, self.camera_subtype, self.camera_rtsp_url,
        )

    @property
    def secrets(self) -> list[str]:
        return [s for s in (self.camera_password, self.smtp_password, self.camera_username) if s]


def build_rtsp_url(ip: str, port: int, user: str, password: str, channel: int,
                   subtype: int, override: str = "") -> str:
    """Dahua format: rtsp://USER:PASS@IP:PORT/cam/realmonitor?channel=N&subtype=M"""
    if override:
        return override
    u, p = quote(user, safe=""), quote(password, safe="")
    return f"rtsp://{u}:{p}@{ip}:{port}/cam/realmonitor?channel={channel}&subtype={subtype}"


def _num(env: dict, key: str, kind, default, errors: list[str], lo=None, hi=None):
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        val = kind(raw)
    except ValueError:
        errors.append(f"{key}: must be a {kind.__name__}")
        return default
    if (lo is not None and val < lo) or (hi is not None and val > hi):
        errors.append(f"{key}: out of range [{lo}, {hi}]")
    return val


def load_config(env_file: str | os.PathLike | None = ".env", environ: dict | None = None,
                check_placeholders: bool = True, require_smtp: bool = True) -> Config:
    """Load from .env file overlaid by process environment (or an explicit dict for tests)."""
    env: dict = {}
    if environ is None:
        if env_file and Path(env_file).exists():
            env.update({k: v for k, v in dotenv_values(env_file).items() if v is not None})
        env.update(os.environ)
    else:
        env.update(environ)

    errors: list[str] = []

    def req(key: str) -> str:
        v = (env.get(key) or "").strip()
        if not v:
            errors.append(f"{key}: required but missing")
        elif check_placeholders and any(m in v for m in PLACEHOLDER_MARKERS):
            errors.append(f"{key}: still contains the .env.example placeholder")
        return v

    def opt(key: str, default: str = "") -> str:
        v = env.get(key)
        return default if v is None else v.strip()

    override = opt("CAMERA_RTSP_URL")
    if override:
        ip = opt("CAMERA_IP", "override")
        user = opt("CAMERA_USERNAME")
        pw = opt("CAMERA_PASSWORD")
    else:
        ip, user, pw = req("CAMERA_IP"), req("CAMERA_USERNAME"), req("CAMERA_PASSWORD")

    transport = opt("CAMERA_RTSP_TRANSPORT", "tcp").lower()
    if transport not in ("tcp", "udp"):
        errors.append("CAMERA_RTSP_TRANSPORT: must be tcp or udp")
    security = opt("SMTP_SECURITY", "starttls").lower()
    if security not in ("starttls", "ssl"):
        errors.append("SMTP_SECURITY: must be starttls or ssl")
    device = opt("DEVICE", "cpu").lower()
    if device not in ("cpu", "cuda"):
        errors.append("DEVICE: must be cpu or cuda")

    if require_smtp:
        smtp_host, smtp_user, smtp_pw = req("SMTP_HOST"), req("SMTP_USERNAME"), req("SMTP_PASSWORD")
        smtp_from, to_raw = req("SMTP_FROM"), req("ALERT_EMAIL_TO")
    else:
        smtp_host, smtp_user, smtp_pw = opt("SMTP_HOST"), opt("SMTP_USERNAME"), opt("SMTP_PASSWORD")
        smtp_from, to_raw = opt("SMTP_FROM"), opt("ALERT_EMAIL_TO")
    recipients = tuple(a.strip() for a in to_raw.replace(";", ",").split(",") if a.strip())
    for a in recipients:
        if "@" not in a:
            errors.append("ALERT_EMAIL_TO: contains an invalid address")
            break

    tz_name = opt("TIMEZONE", "UTC")
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        errors.append(f"TIMEZONE: unknown timezone '{tz_name}'")
        tz = ZoneInfo("UTC")

    cfg = Config(
        camera_name=opt("CAMERA_NAME", "Dahua Camera 1"),
        camera_ip=ip, camera_port=_num(env, "CAMERA_RTSP_PORT", int, 554, errors, 1, 65535),
        camera_username=user, camera_password=pw,
        camera_channel=_num(env, "CAMERA_CHANNEL", int, 1, errors, 0),
        camera_subtype=_num(env, "CAMERA_SUBTYPE", int, 0, errors, 0),
        camera_rtsp_url=override, rtsp_transport=transport,
        connect_timeout=_num(env, "CAMERA_CONNECT_TIMEOUT_SECONDS", float, 10.0, errors, 1),
        stall_timeout=_num(env, "CAMERA_STALL_TIMEOUT_SECONDS", float, 10.0, errors, 1),
        model_id=opt("MODEL_ID", "IDEA-Research/grounding-dino-tiny"),
        model_local_dir=Path(opt("MODEL_LOCAL_DIR", "./models/grounding-dino-tiny")),
        device=device,
        inference_fps=_num(env, "INFERENCE_FPS", float, 1.0, errors, 0.05, 30),
        box_threshold=_num(env, "MODEL_BOX_THRESHOLD", float, 0.30, errors, 0, 1),
        text_threshold=_num(env, "MODEL_TEXT_THRESHOLD", float, 0.25, errors, 0, 1),
        detection_prompt=opt("DETECTION_PROMPT",
                             "thick black smoke plume. dark smoke cloud. smoke rising from industrial equipment."),
        dark_luminance=_num(env, "DARK_PIXEL_LUMINANCE_THRESHOLD", int, 90, errors, 1, 255),
        min_dark_fraction=_num(env, "MIN_DARK_PIXEL_FRACTION", float, 0.40, errors, 0, 1),
        min_motion_fraction=_num(env, "MIN_MOTION_FRACTION", float, 0.03, errors, 0, 1),
        min_detections=_num(env, "MIN_TEMPORAL_DETECTIONS", int, 3, errors, 1),
        min_span_seconds=_num(env, "MIN_DETECTION_SPAN_SECONDS", float, 3.0, errors, 0),
        clear_seconds=_num(env, "EVENT_CLEAR_SECONDS", float, 20.0, errors, 1),
        max_frame_age=_num(env, "MAX_FRAME_AGE_SECONDS", float, 5.0, errors, 0.5),
        smtp_host=smtp_host, smtp_port=_num(env, "SMTP_PORT", int, 587, errors, 1, 65535),
        smtp_security=security, smtp_username=smtp_user, smtp_password=smtp_pw,
        smtp_from=smtp_from, alert_to=recipients,
        smtp_timeout=_num(env, "SMTP_TIMEOUT_SECONDS", float, 20.0, errors, 1),
        email_retry_limit=_num(env, "EMAIL_RETRY_LIMIT", int, 5, errors, 1, 50),
        timezone=tz, data_dir=Path(opt("DATA_DIR", "./data")),
        keep_days=_num(env, "SCREENSHOT_KEEP_DAYS", int, 30, errors, 1),
        log_level=opt("LOG_LEVEL", "INFO").upper(),
    )
    if errors:
        raise ConfigError("Invalid configuration:\n  - " + "\n  - ".join(errors))
    return cfg
