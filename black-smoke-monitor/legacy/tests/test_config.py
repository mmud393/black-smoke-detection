import logging

import pytest

from smoke_monitor.config import ConfigError, load_config
from smoke_monitor.log_setup import RedactingFilter

from conftest import BASE_ENV


def test_dahua_url_and_escaping(cfg):
    assert cfg.rtsp_url == ("rtsp://adm:p%40ss%3Aw%2Frd@192.168.1.100:554/"
                            "cam/realmonitor?channel=1&subtype=0")
    assert "p%40ss" not in cfg.redacted_url and "adm" not in cfg.redacted_url


def test_channel_subtype_override():
    c = load_config(environ={**BASE_ENV, "CAMERA_CHANNEL": "2", "CAMERA_SUBTYPE": "1"})
    assert "channel=2&subtype=1" in c.rtsp_url
    c = load_config(environ={**BASE_ENV, "CAMERA_RTSP_URL": "rtsp://x/y"})
    assert c.rtsp_url == "rtsp://x/y"


def test_missing_and_placeholder_values_fail_without_secrets():
    env = {k: v for k, v in BASE_ENV.items() if k != "SMTP_HOST"}
    env["CAMERA_PASSWORD"] = "replace_with_camera_password"
    with pytest.raises(ConfigError) as e:
        load_config(environ=env)
    msg = str(e.value)
    assert "SMTP_HOST" in msg and "CAMERA_PASSWORD" in msg and "placeholder" in msg and "replace_with" not in msg
    assert "smtpsecret" not in msg


def test_invalid_numbers():
    with pytest.raises(ConfigError, match="INFERENCE_FPS"):
        load_config(environ={**BASE_ENV, "INFERENCE_FPS": "abc"})


def test_log_redaction(cfg, caplog):
    f = RedactingFilter(cfg.secrets)
    rec = logging.LogRecord("x", logging.INFO, "", 0,
                            f"open {cfg.rtsp_url} pw=smtpsecret", None, None)
    f.filter(rec)
    assert "smtpsecret" not in rec.msg and "p%40ss" not in rec.msg and "adm:" not in rec.msg


def test_anthropic_key_required_and_redacted(cfg):
    env = {k: v for k, v in BASE_ENV.items() if k != "ANTHROPIC_API_KEY"}
    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        load_config(environ=env)
    assert load_config(environ=env, require_ai=False).anthropic_api_key == ""
    assert "sk-ant-testkey123" in cfg.secrets


def test_roi_parsing_and_validation():
    c = load_config(environ={**BASE_ENV, "DETECTION_ROI": "0.1,0.1;0.9,0.1;0.5,0.9"})
    assert len(c.detection_roi) == 3
    with pytest.raises(ConfigError, match="DETECTION_ROI"):
        load_config(environ={**BASE_ENV, "DETECTION_ROI": "0.1,0.1;2,0.1;0.5,0.9"})
