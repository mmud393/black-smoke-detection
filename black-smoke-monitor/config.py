"""The only module that reads .env. Produces an immutable, validated Settings object."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"

ENV_TEMPLATE = '''\
# ==============================
# CAMERA: ONE IP CAMERA VIA RTSP
# ==============================
# Example Dahua path; replace with the actual camera's RTSP URL.
# Encode special characters in the RTSP username/password when necessary.
RTSP_URL="rtsp://USERNAME:PASSWORD@CAMERA_IP:554/cam/realmonitor?channel=1&subtype=1"
CAMERA_NAME="Factory Camera"
RTSP_TRANSPORT=tcp
CAMERA_OPEN_TIMEOUT_MS=10000
CAMERA_READ_TIMEOUT_MS=10000
CAMERA_RECONNECT_SECONDS=5
CAMERA_NO_FRAME_TIMEOUT_SECONDS=15

# ==============================
# CONTINUOUS VIDEO PROCESSING
# ==============================
# Number of frames per second submitted to AI inference; it is NOT the camera's FPS.
PROCESS_FPS=2
FRAME_MAX_WIDTH=1280

# ==============================
# PRETRAINED SMOKE AI MODEL
# ==============================
MODEL_REPO_ID=pyronear/yolo11s_sensitive-detector
MODEL_FILENAME=onnx_cpu.tar.gz
MODEL_PATH=./models/pyronear-yolo11s.onnx
MODEL_SMOKE_CLASS_NAME=item
MODEL_CONFIDENCE_MIN=0.25

# ==============================
# BLACK-SMOKE-ONLY VERIFICATION
# ==============================
# Luma: 0=black, 255=white. Tune on actual camera recordings.
BLACK_LUMA_MAX=95
# Fraction of analyzed candidate-region pixels that must be dark.
BLACK_DARK_PIXEL_RATIO_MIN=0.50
# Reject tiny / unreliable candidates, measured on the original processed frame.
SMOKE_REGION_MIN_AREA_PX=300
# Motion difference inside smoke region (for a fixed CCTV camera).
MOTION_PIXEL_DIFFERENCE_MIN=20
MOTION_PIXEL_RATIO_MIN=0.015
# Require multiple positive observations before an alert.
CONFIRMATION_WINDOW_FRAMES=5
CONFIRMATION_POSITIVE_FRAMES=3
# Clear only after this many consecutive seconds without confirmed candidates.
EVENT_CLEAR_SECONDS=20
# Additional minimum time between sent alerts, even for separate events.
EMAIL_COOLDOWN_SECONDS=300

# ==============================
# SCREENSHOT: ONE PER EVENT
# ==============================
SCREENSHOT_DIR=./screenshots
SCREENSHOT_JPEG_QUALITY=90

# ==============================
# EMAIL ALERTS (GMAIL SMTP EXAMPLE)
# ==============================
# Keep false until real credentials + camera are configured and verified.
EMAIL_ENABLED=false
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME="your-sender@gmail.com"
SMTP_PASSWORD="YOUR_GMAIL_APP_PASSWORD"
SMTP_FROM="your-sender@gmail.com"
# One or more email addresses separated by commas.
SMTP_TO="receiver@example.com"
SMTP_TIMEOUT_SECONDS=15
SMTP_RETRIES=2
EMAIL_SUBJECT_PREFIX="BLACK SMOKE DETECTED"

# ==============================
# BASIC DIAGNOSTICS / TIME
# ==============================
APP_TIMEZONE=UTC
LOG_LEVEL=INFO
'''

_RTSP_PLACEHOLDERS = ("USERNAME", "PASSWORD", "CAMERA_IP")
_EMAIL_PLACEHOLDERS = ("your-sender@gmail.com", "YOUR_GMAIL_APP_PASSWORD", "receiver@example.com")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class ConfigError(ValueError):
    """Raised for missing/malformed settings. Messages never contain secret values."""


@dataclass(frozen=True)
class Settings:
    rtsp_url: str
    camera_name: str
    rtsp_transport: str
    camera_open_timeout_ms: int
    camera_read_timeout_ms: int
    camera_reconnect_seconds: float
    camera_no_frame_timeout_seconds: float
    process_fps: float
    frame_max_width: int
    model_repo_id: str
    model_filename: str
    model_path: Path
    model_smoke_class_name: str
    model_confidence_min: float
    black_luma_max: int
    black_dark_pixel_ratio_min: float
    smoke_region_min_area_px: int
    motion_pixel_difference_min: int
    motion_pixel_ratio_min: float
    confirmation_window_frames: int
    confirmation_positive_frames: int
    event_clear_seconds: float
    email_cooldown_seconds: float
    screenshot_dir: Path
    screenshot_jpeg_quality: int
    email_enabled: bool
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_to: tuple = ()
    smtp_timeout_seconds: float = 15
    smtp_retries: int = 2
    email_subject_prefix: str = "BLACK SMOKE DETECTED"
    app_timezone: str = "UTC"
    log_level: str = "INFO"

    def __repr__(self) -> str:  # never leak secrets via repr/logging
        return f"Settings(camera={self.camera_name!r}, email_enabled={self.email_enabled})"

    def rtsp_placeholders(self) -> list[str]:
        """Names of .env keys that still hold template placeholders (for a safe startup refusal)."""
        return ["RTSP_URL"] if all(p in self.rtsp_url for p in _RTSP_PLACEHOLDERS) else []


def redact_url(text: str) -> str:
    """Strip user:password@ from any URL embedded in text (OpenCV/FFmpeg errors can contain them)."""
    return re.sub(r"(://)[^/@\s]*@", r"\1***@", text)


def ensure_env_file(path: Path = ENV_PATH) -> list[str]:
    """Create .env from the template if absent. If present, never modify it; return missing keys."""
    if not path.exists():
        path.write_text(ENV_TEMPLATE, encoding="utf-8")
        return []
    have = set(dotenv_values(path))
    want = {k for k in dotenv_values(stream=io.StringIO(ENV_TEMPLATE))}
    return sorted(want - have)


def _resolve(p: str) -> Path:
    path = Path(p).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def load_settings(env: Mapping[str, str | None] | None = None, env_path: Path = ENV_PATH) -> Settings:
    """Parse and validate. `env` (tests) replaces the .env file entirely; os.environ is not consulted."""
    raw = dict(dotenv_values(env_path)) if env is None else dict(env)
    errors: list[str] = []

    def get(key: str) -> str:
        v = raw.get(key)
        if v is None or str(v).strip() == "":
            errors.append(f"{key} is missing")
            return ""
        return str(v).strip()

    def num(key, cast, lo=None, hi=None, lo_excl=False):
        s = get(key)
        if not s:
            return cast(0)
        try:
            v = cast(s)
        except ValueError:
            errors.append(f"{key} must be a valid {cast.__name__}")
            return cast(0)
        if (lo is not None and (v <= lo if lo_excl else v < lo)) or (hi is not None and v > hi):
            errors.append(f"{key} is out of range")
        return v

    def boolean(key):
        s = get(key).lower()
        if s not in ("true", "false"):
            if s:
                errors.append(f"{key} must be true or false")
            return False
        return s == "true"

    rtsp_url = get("RTSP_URL")
    if rtsp_url:
        u = urlsplit(rtsp_url)
        if u.scheme not in ("rtsp", "rtsps") or not u.hostname:
            errors.append("RTSP_URL must be an rtsp:// URL with a host")
    transport = get("RTSP_TRANSPORT").lower()
    if transport and transport not in ("tcp", "udp"):
        errors.append("RTSP_TRANSPORT must be tcp or udp")
    s = dict(
        rtsp_url=rtsp_url,
        camera_name=get("CAMERA_NAME"),
        rtsp_transport=transport,
        camera_open_timeout_ms=num("CAMERA_OPEN_TIMEOUT_MS", int, 0, lo_excl=True),
        camera_read_timeout_ms=num("CAMERA_READ_TIMEOUT_MS", int, 0, lo_excl=True),
        camera_reconnect_seconds=num("CAMERA_RECONNECT_SECONDS", float, 0, lo_excl=True),
        camera_no_frame_timeout_seconds=num("CAMERA_NO_FRAME_TIMEOUT_SECONDS", float, 0, lo_excl=True),
        process_fps=num("PROCESS_FPS", float, 0, lo_excl=True),
        frame_max_width=num("FRAME_MAX_WIDTH", int, 15),
        model_repo_id=get("MODEL_REPO_ID"),
        model_filename=get("MODEL_FILENAME"),
        model_path=_resolve(get("MODEL_PATH") or "."),
        model_smoke_class_name=get("MODEL_SMOKE_CLASS_NAME"),
        model_confidence_min=num("MODEL_CONFIDENCE_MIN", float, 0, 1),
        black_luma_max=num("BLACK_LUMA_MAX", int, 0, 255),
        black_dark_pixel_ratio_min=num("BLACK_DARK_PIXEL_RATIO_MIN", float, 0, 1),
        smoke_region_min_area_px=num("SMOKE_REGION_MIN_AREA_PX", int, 0),
        motion_pixel_difference_min=num("MOTION_PIXEL_DIFFERENCE_MIN", int, 0, 255),
        motion_pixel_ratio_min=num("MOTION_PIXEL_RATIO_MIN", float, 0, 1),
        confirmation_window_frames=num("CONFIRMATION_WINDOW_FRAMES", int, 1),
        confirmation_positive_frames=num("CONFIRMATION_POSITIVE_FRAMES", int, 1),
        event_clear_seconds=num("EVENT_CLEAR_SECONDS", float, 0, lo_excl=True),
        email_cooldown_seconds=num("EMAIL_COOLDOWN_SECONDS", float, 0),
        screenshot_dir=_resolve(get("SCREENSHOT_DIR") or "."),
        screenshot_jpeg_quality=num("SCREENSHOT_JPEG_QUALITY", int, 1, 100),
        email_enabled=boolean("EMAIL_ENABLED"),
        smtp_host=get("SMTP_HOST"),
        smtp_port=num("SMTP_PORT", int, 1, 65535),
        smtp_username=get("SMTP_USERNAME"),
        smtp_password=get("SMTP_PASSWORD"),
        smtp_from=get("SMTP_FROM"),
        smtp_to=tuple(a.strip() for a in get("SMTP_TO").split(",") if a.strip()),
        smtp_timeout_seconds=num("SMTP_TIMEOUT_SECONDS", float, 0, lo_excl=True),
        smtp_retries=num("SMTP_RETRIES", int, 0),
        email_subject_prefix=get("EMAIL_SUBJECT_PREFIX"),
        app_timezone=get("APP_TIMEZONE"),
        log_level=get("LOG_LEVEL").upper(),
    )
    if s["confirmation_positive_frames"] > s["confirmation_window_frames"]:
        errors.append("CONFIRMATION_POSITIVE_FRAMES must be <= CONFIRMATION_WINDOW_FRAMES")
    if s["log_level"] and s["log_level"] not in _LOG_LEVELS:
        errors.append("LOG_LEVEL must be one of " + ", ".join(sorted(_LOG_LEVELS)))
    if s["app_timezone"]:
        try:
            ZoneInfo(s["app_timezone"])
        except (ZoneInfoNotFoundError, ValueError):
            errors.append("APP_TIMEZONE is not a valid timezone")
    if s["email_enabled"]:
        if s["smtp_port"] == 465:
            errors.append("SMTP_PORT 465 (implicit TLS) is not supported; use STARTTLS (e.g. 587)")
        for key in ("smtp_username", "smtp_password", "smtp_from"):
            if s[key] in _EMAIL_PLACEHOLDERS:
                errors.append(f"{key.upper()} still holds a placeholder")
        for a in s["smtp_to"]:
            if a in _EMAIL_PLACEHOLDERS:
                errors.append("SMTP_TO still holds a placeholder")
        if s["smtp_from"] and not _EMAIL_RE.match(s["smtp_from"]):
            errors.append("SMTP_FROM is not a valid email address")
        if not s["smtp_to"] or not all(_EMAIL_RE.match(a) for a in s["smtp_to"]):
            errors.append("SMTP_TO must be one or more valid email addresses")
    if errors:
        raise ConfigError("Invalid .env: " + "; ".join(dict.fromkeys(errors)))
    return Settings(**s)
