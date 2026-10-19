import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from smoke_monitor.config import load_config

BASE_ENV = {
    "CAMERA_IP": "192.168.1.100", "CAMERA_USERNAME": "adm", "CAMERA_PASSWORD": "p@ss:w/rd",
    "SMTP_HOST": "smtp.example.org", "SMTP_USERNAME": "u@example.org", "SMTP_PASSWORD": "smtpsecret",
    "ANTHROPIC_API_KEY": "sk-ant-testkey123",
    "SMTP_FROM": "u@example.org", "ALERT_EMAIL_TO": "boss@example.org", "TIMEZONE": "Asia/Karachi",
}


@pytest.fixture
def cfg(tmp_path):
    return load_config(environ={**BASE_ENV, "DATA_DIR": str(tmp_path)})
