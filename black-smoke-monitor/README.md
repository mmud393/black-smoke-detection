# Black Smoke Monitor

One Dahua IP camera → continuous monitoring → pretrained model (Grounding DINO Tiny, no training) finds smoke candidates → dark-appearance + motion + temporal checks → annotated screenshot → one email per smoke episode → keeps monitoring. No UI, API, database or accounts.

**Limits:** AI-generated warning only. Not a certified fire alarm; keep certified detectors and site procedures. Thresholds in `.env` are starting heuristics that need on-site testing; accuracy has **not** been field-validated. Email needs internet or a reachable SMTP server.

## Setup (Ubuntu; macOS works for development)
```bash
sudo apt install -y python3 python3-venv ffmpeg      # macOS: brew install ffmpeg
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && chmod 600 .env               # fill in camera + SMTP values
python scripts/test_camera.py          # verifies RTSP + decodes frames
python scripts/download_model.py       # once, needs internet (~700 MB); then runs offline
python scripts/benchmark.py            # real inference speed on this host; lower INFERENCE_FPS if too slow
python -m smoke_monitor.test_email     # only when you want to send one TEST email
python -m smoke_monitor                # run in foreground first and watch the logs
pytest                                  # unit tests (no camera/SMTP needed)
```

Dahua RTSP: `rtsp://USER:PASS@IP:554/cam/realmonitor?channel=1&subtype=0` (subtype=1 = substream). Built from `.env` parts with credentials percent-encoded; override with `CAMERA_RTSP_URL`. Logs redact credentials.

## Offline replay
```bash
python scripts/replay_video.py --video clip.mp4 --dry-run-email   # real model, prints JSON, never sends
python scripts/replay_video.py --video clip.mp4 --stub-detector   # TEST-ONLY fixed box, checks the flow
```

## systemd (production)
```bash
sudo useradd -r -s /usr/sbin/nologin smokemon
sudo cp -r . /opt/black-smoke-monitor && sudo chown -R smokemon: /opt/black-smoke-monitor
sudo chmod 600 /opt/black-smoke-monitor/.env
sudo cp deploy/black-smoke-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now black-smoke-monitor
systemctl status black-smoke-monitor
journalctl -u black-smoke-monitor -f          # also data/logs/smoke_monitor.log (rotated)
sudo systemctl restart black-smoke-monitor    # stop: sudo systemctl stop black-smoke-monitor
```
(Create the venv and model inside `/opt/black-smoke-monitor` as that user.)

## How it decides
1. Sample frames at `INFERENCE_FPS`; skip frames older than `MAX_FRAME_AGE_SECONDS`.
2. Model proposes boxes for `DETECTION_PROMPT`.
3. Per box: dark-pixel fraction, brightness quantiles, contrast vs surroundings; mostly-light regions = steam/white smoke (rejected); dark but static = machine/shadow (rejected); whole-scene change = camera shake (uncertain, rejected); dark **and** moving = candidate.
4. `CLEAR → SUSPECTED → ALERTED → CLEARING → CLEAR`: needs `MIN_TEMPORAL_DETECTIONS` associated hits spanning `MIN_DETECTION_SPAN_SECONDS`. One email per episode; re-arms after `EVENT_CLEAR_SECONDS` without smoke. A restart within 10 min of an active alert does not re-alert.
5. Emails go through `data/email_outbox/` with bounded exponential retry (`EMAIL_RETRY_LIMIT`); `.sent` means *accepted by SMTP*, not delivered. Screenshots older than `SCREENSHOT_KEEP_DAYS` are deleted.

## Troubleshooting
- **Camera offline:** same network? port 554 open? RTSP enabled on camera? H.264? Test in VLC; try `CAMERA_SUBTYPE=1`. Logs show `Camera unavailable; reconnecting`. No email is sent for outages.
- **No emails:** run `python -m smoke_monitor.test_email`; check `*.json` (pending) / `*.failed` in `data/email_outbox/` and the logs. Gmail needs an app password.
- **Slow inference:** `health` log lines and the "Degraded" warning; lower `INFERENCE_FPS` or use a stronger host.
- **Field checklist:** review real footage of black smoke vs dark machinery, shadows, steam, clouds, dusk/night, rain before trusting thresholds.
