import threading
import time
from datetime import datetime, timezone

import cv2
import numpy as np

import email_alert
import main
from detector import Candidate, Verdict
from email_alert import EmailWorker, build_message, save_screenshot

WHEN = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
FRAME = np.full((100, 100, 3), 60, np.uint8)
VERDICT = Verdict(True, Candidate((10, 10, 60, 60), 0.9), 0.8, 0.2)


def test_screenshot_is_decodable_jpeg_and_frame_untouched(settings):
    before = FRAME.copy()
    p = save_screenshot(settings, FRAME, (10, 10, 60, 60), WHEN)
    assert cv2.imread(str(p)) is not None and p.suffix == ".jpg"
    assert (FRAME == before).all()


def test_message_has_one_jpeg_attachment_and_recipients(mk):
    s = mk(SMTP_TO="a@b.co,c@d.co")
    p = save_screenshot(s, FRAME, (10, 10, 60, 60), WHEN)
    msg = build_message(s, p, WHEN, 0.9, 0.8)
    atts = list(msg.iter_attachments())
    assert len(atts) == 1 and atts[0].get_content_type() == "image/jpeg"
    assert msg["To"] == "a@b.co, c@d.co" and s.camera_name in msg["Subject"]


def test_disabled_email_never_touches_smtp(settings, monkeypatch):
    monkeypatch.setattr(email_alert.smtplib, "SMTP", lambda *a, **k: (_ for _ in ()).throw(AssertionError("SMTP used")))
    main.handle_event(settings, FRAME, VERDICT, worker=None)
    assert len(list(settings.screenshot_dir.glob("*.jpg"))) == 1


def test_smtp_uses_starttls_and_login(mk, monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout): calls.append(("conn", host, port))
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def ehlo(self): calls.append("ehlo")
        def starttls(self, context): calls.append("starttls")
        def login(self, u, p): calls.append("login")
        def send_message(self, m): calls.append("send")

    monkeypatch.setattr(email_alert.smtplib, "SMTP", FakeSMTP)
    email_alert.send_via_smtp(mk(), object())
    assert calls.index("starttls") < calls.index("login") < calls.index("send")


def test_worker_retries_boundedly_and_never_blocks(mk):
    s = mk(SMTP_RETRIES=2)
    attempts, done = [], threading.Event()

    def failing(_s, _m):
        attempts.append(1)
        if len(attempts) == 3:
            done.set()
        raise OSError("down")

    w = EmailWorker(s, sender=failing, retry_delay=0.01)
    t0 = time.monotonic()
    assert w.submit(object())
    assert time.monotonic() - t0 < 0.1
    assert done.wait(2)
    time.sleep(0.1)
    w.close()
    assert len(attempts) == 3  # 1 try + 2 retries, no more


def test_no_email_without_confirmed_event(settings):
    sent = []

    class W:
        def submit(self, m): sent.append(m)

    from detector import EventTracker
    t = EventTracker(settings)
    for i in range(10):
        assert not t.observe(False, i)
    assert sent == []
