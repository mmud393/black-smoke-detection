import os
import signal
import subprocess
import sys


def test_starts_reports_idle_and_stops_on_sigterm():
    env = {**os.environ, "APP_ENV": "test", "LOG_LEVEL": "INFO"}
    p = subprocess.Popen([sys.executable, "-m", "smoke_worker"], stdout=subprocess.PIPE, text=True, env=env)
    line = p.stdout.readline()
    assert "IDLE_NOT_MONITORING" in line and '"monitoring": false' in line
    p.send_signal(signal.SIGTERM)
    out, _ = p.communicate(timeout=10)
    assert p.returncode == 0 and "STOPPED" in out


def test_bad_config_exits_2_with_message():
    env = {**os.environ, "FACTORY_TIMEZONE": "Mars/Base"}
    cmd = [sys.executable, "-m", "smoke_worker"]
    r = subprocess.run(cmd, check=False, capture_output=True, text=True, env=env, timeout=20)
    assert r.returncode == 2 and "FACTORY_TIMEZONE" in r.stderr
