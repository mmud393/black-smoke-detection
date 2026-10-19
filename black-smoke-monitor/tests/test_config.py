import io
import pytest
from dotenv import dotenv_values

import config
from config import ConfigError, load_settings, redact_url
from conftest import make_env


def test_every_template_key_is_loaded(tmp_path):
    keys = set(dotenv_values(stream=io.StringIO(config.ENV_TEMPLATE)))
    from dataclasses import fields
    assert keys == {f.name.upper() for f in fields(config.Settings)}
    s = load_settings(make_env(tmp_path))
    assert s.process_fps == 2 and s.confirmation_positive_frames == 3 and s.smtp_to == ("receiver@example.com",)
    assert s.email_enabled is False and s.model_path.is_absolute()


def test_missing_key_is_reported_without_secrets(tmp_path):
    env = make_env(tmp_path, SMTP_PASSWORD="topsecret")
    del env["RTSP_URL"]
    with pytest.raises(ConfigError) as e:
        load_settings(env)
    assert "RTSP_URL" in str(e.value) and "topsecret" not in str(e.value)


def test_bad_rtsp_url(mk):
    with pytest.raises(ConfigError, match="RTSP_URL"):
        mk(RTSP_URL="http://x")


def test_email_placeholders_only_ok_while_disabled(mk):
    mk(EMAIL_ENABLED="false")
    with pytest.raises(ConfigError, match="placeholder"):
        mk(EMAIL_ENABLED="true")
    mk(EMAIL_ENABLED="true", SMTP_USERNAME="a@b.co", SMTP_PASSWORD="x", SMTP_FROM="a@b.co", SMTP_TO="c@d.co,e@f.co")


@pytest.mark.parametrize("key,val", [
    ("MODEL_CONFIDENCE_MIN", 1.5), ("BLACK_DARK_PIXEL_RATIO_MIN", -0.1), ("SCREENSHOT_JPEG_QUALITY", 0),
    ("SCREENSHOT_JPEG_QUALITY", 101), ("PROCESS_FPS", 0), ("BLACK_LUMA_MAX", 300), ("SMTP_PORT", 70000),
    ("APP_TIMEZONE", "Nope/Zone"), ("EMAIL_ENABLED", "yes"), ("LOG_LEVEL", "LOUD"),
])
def test_invalid_values_rejected(mk, key, val):
    with pytest.raises(ConfigError):
        mk(**{key: val})


def test_positive_frames_cannot_exceed_window(mk):
    with pytest.raises(ConfigError, match="CONFIRMATION_POSITIVE_FRAMES"):
        mk(CONFIRMATION_WINDOW_FRAMES=2, CONFIRMATION_POSITIVE_FRAMES=3)


def test_placeholder_rtsp_detected_and_repr_safe(mk):
    s = mk(SMTP_PASSWORD="hunter2")
    assert s.rtsp_placeholders() == ["RTSP_URL"]
    assert "hunter2" not in repr(s)
    assert mk(RTSP_URL="rtsp://u:p@10.0.0.5:554/x").rtsp_placeholders() == []


def test_redact_url():
    assert "pw" not in redact_url("open rtsp://admin:pw@1.2.3.4/x failed")


def test_ensure_env_file_creates_then_preserves(tmp_path):
    p = tmp_path / ".env"
    assert config.ensure_env_file(p) == []
    p.write_text("RTSP_URL=rtsp://a:b@c/d\n")
    missing = config.ensure_env_file(p)
    assert "PROCESS_FPS" in missing and p.read_text() == "RTSP_URL=rtsp://a:b@c/d\n"
