from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from smoke_monitor.ai_confirm import ClaudeConfirmer, parse_verdict


@pytest.mark.parametrize("text,ok,verdict", [
    ("VERDICT: YES\nREASON: thick dark plume", True, "yes"),
    ("verdict: no\nreason: white steam", False, "no"),
    ("VERDICT: UNSURE\nREASON: blurry", False, "unsure"),
    ("It looks like smoke to me", False, "unsure"),
])
def test_parse_verdict(text, ok, verdict):
    v = parse_verdict(text)
    assert v.confirmed is ok and v.verdict == verdict


class FakeClient:
    def __init__(self, text=None, stop_reason="end_turn", exc=None):
        self.messages, self.sent = self, None
        self._text, self._stop, self._exc = text, stop_reason, exc

    def create(self, **kw):
        self.sent = kw
        if self._exc:
            raise self._exc
        return SimpleNamespace(stop_reason=self._stop,
                               content=[SimpleNamespace(type="text", text=self._text)])


@pytest.fixture
def jpg(tmp_path):
    p = tmp_path / "s.jpg"
    cv2.imwrite(str(p), np.full((2000, 3000, 3), 90, np.uint8))
    return p


def test_yes_sends_downscaled_image_and_confirms(jpg):
    client = FakeClient("VERDICT: YES\nREASON: dark plume")
    v = ClaudeConfirmer("k", "claude-opus-5-5", client=client).confirm(jpg)
    assert v.confirmed
    block = client.sent["messages"][0]["content"][0]
    assert block["type"] == "image" and block["source"]["media_type"] == "image/jpeg"
    assert client.sent["model"] == "claude-opus-5-5"


def test_errors_refusals_and_bad_files_fail_closed(jpg, tmp_path):
    assert not ClaudeConfirmer("k", "m", client=FakeClient(exc=RuntimeError("boom"))).confirm(jpg).confirmed
    assert ClaudeConfirmer("k", "m", client=FakeClient("", "refusal")).confirm(jpg).verdict == "refusal"
    assert ClaudeConfirmer("k", "m", client=FakeClient("VERDICT: YES")).confirm(tmp_path / "missing.jpg").verdict == "error"
