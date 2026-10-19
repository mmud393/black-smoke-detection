"""Second opinion from Claude: an email is sent only if Claude confirms black/dark smoke."""
from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import cv2

log = logging.getLogger(__name__)

MAX_SIDE = 1568  # larger images are downscaled by the API anyway
PROMPT = (
    "This frame is from an industrial site camera. A motion detector flagged the area inside "
    "the red rectangle as possible BLACK or DARK smoke. Look at the whole image.\n"
    "Answer YES only if the flagged area clearly shows a plume or cloud of black/dark smoke. "
    "Answer NO for white or gray steam, clouds, dust, fog, shadows, dark machinery, vehicles, "
    "people, fire without dark smoke, or lens/lighting artifacts. Answer UNSURE if the image "
    "is too unclear to tell. Do not guess: a wrong YES triggers an emergency email.\n"
    "Reply in exactly this format:\n"
    "VERDICT: YES|NO|UNSURE\n"
    "REASON: <one short sentence>"
)
_VERDICT = re.compile(r"VERDICT:\s*(YES|NO|UNSURE)", re.IGNORECASE)
_REASON = re.compile(r"REASON:\s*(.+)", re.IGNORECASE)


@dataclass(frozen=True)
class AIVerdict:
    confirmed: bool
    verdict: str   # yes | no | unsure | error | refusal
    reason: str


def parse_verdict(text: str) -> AIVerdict:
    m = _VERDICT.search(text)
    if not m:
        return AIVerdict(False, "unsure", "unparseable reply")
    verdict = m.group(1).lower()
    r = _REASON.search(text)
    return AIVerdict(verdict == "yes", verdict, (r.group(1).strip() if r else "")[:300])


def prepare_image(path: Path) -> bytes:
    """JPEG bytes of the screenshot, downscaled so the long side is <= MAX_SIDE."""
    img = cv2.imread(str(path))
    if img is None:
        raise ValueError("cannot read screenshot")
    h, w = img.shape[:2]
    scale = MAX_SIDE / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise ValueError("JPEG encoding failed")
    return buf.tobytes()


class ClaudeConfirmer:
    """Sends the annotated screenshot to Claude and returns a conservative verdict.
    Any error, refusal or unclear answer means NOT confirmed (no email)."""

    def __init__(self, api_key: str, model: str, timeout: float = 30.0, client=None):
        if client is None:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=2)
        self.client, self.model = client, model

    def confirm(self, image_path: Path) -> AIVerdict:
        try:
            data = base64.standard_b64encode(prepare_image(Path(image_path))).decode()
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                output_config={"effort": "low"},
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64",
                                                 "media_type": "image/jpeg", "data": data}},
                    {"type": "text", "text": PROMPT},
                ]}],
            )
        except Exception as exc:  # noqa: BLE001 - API/network/image errors: fail closed
            log.warning("AI confirmation failed (%s); treating as not confirmed", type(exc).__name__)
            return AIVerdict(False, "error", type(exc).__name__)
        if response.stop_reason == "refusal":
            return AIVerdict(False, "refusal", "model declined")
        text = "".join(b.text for b in response.content if b.type == "text")
        return parse_verdict(text)
