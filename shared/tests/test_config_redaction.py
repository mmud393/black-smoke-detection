import pytest
from smoke_shared.config import ConfigError, load_settings
from smoke_shared.redaction import redact, redact_text


def test_production_requires_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_SECRET_KEY", "CHANGE_ME_GENERATE_RANDOM")
    with pytest.raises(ConfigError) as e:
        load_settings()
    assert "APP_SECRET_KEY" in str(e.value)


def test_bad_timezone_message(monkeypatch):
    monkeypatch.setenv("FACTORY_TIMEZONE", "Mars/Base")
    with pytest.raises(ConfigError) as e:
        load_settings()
    assert "FACTORY_TIMEZONE" in str(e.value)


def test_redaction():
    assert "hunter2" not in redact_text("open rtsp://admin:hunter2@10.0.0.5/stream failed")
    out = redact({"smtp_password": "x", "nested": {"url": "rtsp://u:p@h/s"}, "ok": 1})
    assert out["smtp_password"] == "[REDACTED]" and "p@" not in out["nested"]["url"] and out["ok"] == 1
