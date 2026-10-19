from datetime import datetime, timezone

import pytest

from smoke_monitor.email_alert import EmailWorker, Outbox, build_message


@pytest.fixture
def jpg(tmp_path):
    p = tmp_path / "black_smoke_x.jpg"
    p.write_bytes(b"\xff\xd8JPEGBYTES")
    return p


def test_message_has_attachment_and_subject(cfg, jpg):
    m = build_message(cfg, jpg, datetime(2026, 10, 17, 17, 42, tzinfo=timezone.utc))
    assert m["Subject"] == "[BLACK SMOKE ALERT] Dahua Camera 1 - 2026-10-17 22:42 PKT"
    att = list(m.iter_attachments())[0]
    assert att.get_payload(decode=True) == jpg.read_bytes() and att.get_filename() == jpg.name
    assert "AI-generated warning" in m.get_body().get_content()


def test_retry_backoff_bounded_then_failed_and_survives_restart(cfg, jpg, tmp_path):
    box = Outbox(tmp_path / "ob")
    box.enqueue("e1", jpg, datetime.now(timezone.utc))
    calls = []

    def bad(c, m):
        calls.append(1)
        raise OSError("smtp down")

    w = EmailWorker(cfg, box, sender=bad)
    t = 1000.0
    w.process_once(t)
    assert len(calls) == 1 and box.pending_count() == 1
    w.process_once(t + 1)  # backoff not elapsed
    assert len(calls) == 1
    # "restart": brand-new worker + outbox objects read the same files
    w2 = EmailWorker(cfg, Outbox(tmp_path / "ob"), sender=bad)
    for i in range(1, 10):
        w2.process_once(t + i * 10_000)
    assert len(calls) == cfg.email_retry_limit
    assert box.pending_count() == 0 and list((tmp_path / "ob").glob("*.failed"))


def test_success_marks_accepted(cfg, jpg, tmp_path):
    box = Outbox(tmp_path / "ob")
    box.enqueue("e2", jpg, datetime.now(timezone.utc))
    sent = []
    EmailWorker(cfg, box, sender=lambda c, m: sent.append(m)).process_once()
    assert len(sent) == 1 and (tmp_path / "ob" / "e2.sent").exists() and box.pending_count() == 0
