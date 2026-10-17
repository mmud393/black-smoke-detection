"""Typed environment configuration shared by API and worker."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .enums import AppEnv

_PLACEHOLDERS = {"", "CHANGE_ME_GENERATE_RANDOM", "REPLACE_ME"}


class ConfigError(Exception):
    """Raised with a human-readable explanation of invalid configuration."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: AppEnv = AppEnv.DEVELOPMENT
    factory_name: str = "Example Factory"
    factory_timezone: str = "UTC"
    data_dir: Path = Path("./data")
    database_url: str = ""  # defaults to sqlite under data_dir; used from Step 02
    app_secret_key: str = ""
    allowed_origins: str = "http://localhost:5173"
    session_cookie_secure: bool = False
    log_level: str = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = Field(8000, ge=1, le=65535)
    expose_api_docs: bool = False

    # secrets / auth
    camera_credential_encryption_key: str = ""  # Fernet key; or *_file
    camera_credential_encryption_key_file: Path | None = None
    camera_allowed_cidrs: str = ""  # comma-separated; empty = any non-loopback host
    setup_token: str = ""  # required by POST /setup/initial-admin (local bootstrap)
    session_ttl_hours: int = Field(12, ge=1, le=720)
    login_max_failures: int = Field(5, ge=1)
    login_lockout_seconds: int = Field(300, ge=1)

    # model
    model_backend: str = "grounding_dino"
    model_id: str = "IDEA-Research/grounding-dino-base"
    model_revision: str = ""
    model_device: str = "auto"
    model_cache_dir: Path = Path("./models")
    hf_hub_offline: bool = True
    max_concurrent_inferences: int = Field(1, ge=1)
    demo_mode: bool = False  # enables visibly-labeled fake detector/test incidents

    # pipeline defaults
    camera_stale_seconds: float = 10.0
    evidence_retention_days: int = 30
    evidence_max_gb: float = 20.0
    alert_cooldown_seconds: int = 300

    # smtp (password may also be stored encrypted via settings API)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_tls_mode: str = "starttls"  # starttls | ssl
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_to: str = ""
    smtp_timeout_seconds: int = 20
    smtp_max_attempts: int = 5
    smtp_delivery_enabled: bool = False
    smtp_attachment_max_bytes: int = 3_000_000
    dashboard_url: str = ""

    @field_validator("log_level")
    @classmethod
    def _level(cls, v: str) -> str:
        v = v.upper()
        if v not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL")
        return v

    @field_validator("factory_timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown IANA timezone '{v}' (example: Asia/Karachi)") from exc
        return v

    @model_validator(mode="after")
    def _production_rules(self) -> Settings:
        if self.app_env is AppEnv.PRODUCTION:
            if self.app_secret_key in _PLACEHOLDERS or len(self.app_secret_key) < 32:
                raise ValueError(
                    "APP_SECRET_KEY must be set to a random value of at least 32 characters "
                    "in production (e.g. `python -c \"import secrets;print(secrets.token_urlsafe(48))\"`)"
                )
            if not self.session_cookie_secure:
                raise ValueError("SESSION_COOKIE_SECURE must be true in production (serve over HTTPS)")
            if self.expose_api_docs:
                raise ValueError("EXPOSE_API_DOCS must be false in production")
        return self

    @property
    def encryption_key(self) -> str:
        if self.camera_credential_encryption_key:
            return self.camera_credential_encryption_key
        if self.camera_credential_encryption_key_file:
            return self.camera_credential_encryption_key_file.read_text().strip()
        return ""

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def effective_database_url(self) -> str:
        return self.database_url or f"sqlite:///{(self.data_dir / 'monitor.db').resolve()}"


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        lines = ["Invalid configuration:"]
        for err in exc.errors():
            name = ".".join(str(p) for p in err["loc"]).upper() or "settings"
            lines.append(f"  - {name}: {err['msg'].removeprefix('Value error, ')}")
        lines.append("See .env.example for documented settings.")
        raise ConfigError("\n".join(lines)) from None
