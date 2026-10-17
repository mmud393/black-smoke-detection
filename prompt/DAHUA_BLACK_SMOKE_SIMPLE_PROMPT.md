# MASTER BUILD PROMPT — Simple 24/7 Dahua Black-Smoke Email Monitor

**Paste this entire file into your AI coding agent (Cursor, Codex, Claude Code, etc.).**

## 1. Your role and the exact goal

You are a senior Python engineer, computer-vision engineer, and Linux operations engineer. **Build the actual runnable software project**, not merely an explanation or architectural proposal.

The company has **one Dahua IP camera**. Write a small background Python application that:

1. Connects to that camera's RTSP feed.
2. **Continuously monitors** the camera, 24 hours a day, 7 days a week, while the host computer is powered and reachable.
3. Uses an **existing pretrained AI model (NO custom model training)** to find smoke candidates.
4. Uses additional image and temporal checks to **alert only when it has evidence of black/dark smoke**, rather than white steam, ordinary white/light-gray smoke, clouds, shadows, or unrelated dark objects.
5. When a new black-smoke event passes the detection rules, captures the camera frame, draws a rectangle around the detected region, and saves the screenshot with a UTC timestamp.
6. **Immediately queues/sends an email** to the configured recipient(s) with the screenshot attached and an understandable alert subject/body.
7. Continues monitoring after sending an email. If smoke remains present, **send one email per continuous smoke episode**, not an email for every video frame; when smoke clears and later returns, send another email.
8. Automatically reconnects after stream interruptions and restarts if the process crashes or the computer reboots.

This is a **simple, unattended local monitoring service**. It is **not** an alarm dashboard, mobile app, or cloud service.

### Absolute scope restrictions — do NOT build any of these

- **NO sign-up, account creation, login, user roles, authentication UI, or user management.** The application itself has no user accounts.
- **NO frontend, website, React, dashboard, camera management UI, browser controls, FastAPI REST API, Node.js, or mobile app.**
- **NO SQL database, analytics dashboards, charts, manual review queues, or audit portal.**
- **NO custom training or fine-tuning**, dataset collection workflows, labeling tools, paid AI APIs, Roboflow hosted inference, or cloud AI.
- **NO subscription-dependent services, cloud storage, hosting, paid message services, GPU cloud, or unnecessary infrastructure.**
- **NO fire/people/vehicle/white-smoke alerts.** Alert email must be for verified **suspected black/dark smoke** only.
- **NO emails for routine frames**, no normal-status digest, and no camera-offline emails unless explicitly requested later. Connection failures go to local logs.
- **NO continuous video recordings.** Capture a small number of screenshots for actual detection events only.

A configured SMTP email address/account **is required to send emails**, but do **not** create a login/account system for the monitoring application.

## 2. Reality and safety constraints

**Do not claim perfect detection.** A freely available, general-purpose pretrained object detector is not guaranteed to reliably distinguish black smoke from steam, darkness, shadows, dust, or night-time artifacts at the actual installation. A bounding box with many dark pixels does not prove the pixels are smoke. False negatives and false positives remain possible even after temporal filtering. Use conservative verification, sensible thresholds, testing and honest logging; clearly document limitations. Never advertise 100% accuracy or claim this is a certified fire alarm.

The factory must not rely on this software as its sole fire/emergency protection. Certified detectors and the site's existing safety procedures remain necessary. The software should run even when the internet is unavailable; email notifications necessarily require internet or access to an SMTP server.

## 3. Final fixed technology stack (minimal)

| Part | Use | Why |
|------|-----|-----|
| Language | Python 3.11+ | One simple codebase |
| IP camera | Dahua RTSP | Existing physical camera |
| Frame capture | OpenCV with FFmpeg backend | Continuous frame decoding |
| Detection | Hugging Face Transformers + PyTorch | Local pretrained inference |
| Pretrained model | `IDEA-Research/grounding-dino-tiny` | Apache-2.0 zero-shot detector; no training; test first |
| Color/motion verification | OpenCV + NumPy | Check darkness, motion, temporal persistence |
| Screenshots | OpenCV JPEG | Evidence image and bounding box |
| Email | Python `smtplib` + `email.message.EmailMessage` | No paid API required |
| Config | `.env` (python-dotenv) | Simple user-provided settings |
| Continuous service | `systemd` on Ubuntu Linux | Start at boot, restart after crash |
| Logging | Python `logging` + rotating file handler | Diagnose failures without a database |
| Tests | `pytest` | Validate detection workflow |

Use only **locally executed** code and models. The Grounding DINO Tiny model currently declares Apache-2.0 at https://huggingface.co/IDEA-Research/grounding-dino-tiny . **Recheck the exact revision and third-party dependency licenses when packaging.** Prefer model files in safe `safetensors` format, pin model revision once verified, and retain required license/attribution notices.

Do NOT silently switch to Ultralytics' AGPL implementation or unrelated weights; internal proprietary uses may have different licensing requirements. Do not imply model licensing automatically establishes detection quality.

You may choose a different **verified, permissively licensed, locally runnable pretrained model** only if the default cannot detect smoke or cannot perform on the host, and you document the reason, model revision, inference changes and license. Do not silently add a second model or complex AI system without evidence it is needed. **Never train a custom model.**

## 4. Dahua camera RTSP URL — IMPORTANT

User originally supplied this format:

```text
rtsp://Username:Password@IP Address/streaming/channels/102/
```

This is not the standard Dahua RTSP path; it resembles Hikvision's stream scheme. **Use Dahua's documented format instead**:

**Main stream (preferred for AI detection):**

```text
rtsp://USERNAME:PASSWORD@192.168.1.100:554/cam/realmonitor?channel=1&subtype=0
```

**Substream (only if main is too heavy or connection requires it):**

```text
rtsp://USERNAME:PASSWORD@192.168.1.100:554/cam/realmonitor?channel=1&subtype=1
```

`192.168.1.100` is an **example** placeholder, not the user's actual IP. Channel `1` is the first channel and `subtype=0` is the main stream. Some Dahua NVRs, alternate firmware or channel setups differ; allow the complete RTSP path/port to be overridden in `.env` and test it rather than guessing. The chosen stream should be H.264 where possible for compatibility. Prefer RTSP over TCP. If credentials include special URL characters, encode them correctly, or construct a URL securely from separate settings; never print full credentials in logs.

**Camera troubleshooting:** Document checking camera and server on the same reachable network, RTSP port (normally 554), selecting the proper channel, enabling RTSP, video encoding H.264, verifying feed in VLC, and checking firewall/access restrictions. NEVER ask the user to paste actual passwords into public logs or source code.

## 5. Behavior in exact sequence

```text
APP START
  |
  +--> Read and validate .env configuration
  |
  +--> Load local pretrained AI model ONCE; fail clearly if unavailable
  |
  +--> Connect to Dahua RTSP main stream over TCP
  |
  +--> Continuously read fresh frames into bounded latest-frame buffer
           |
           +--> Sample frames at configurable inference rate (initially 1 FPS on CPU)
           |
           +--> Pretrained AI looks for possible smoke plume regions
           |
           +--> Discard invalid/non-smoke candidates
           |
           +--> Verify candidate's darkness AND temporal/motion appearance
           |
           +--> If no verified black-smoke event: do not email
           |
           +--> If verified NEW black-smoke event:
                 |
                 +--> Capture original frame
                 +--> Annotate detected smoke region + timestamp
                 +--> Save JPEG evidence
                 +--> Send email with JPEG attachment
                 +--> Mark same episode as alerted
                 +--> Keep monitoring
           |
           +--> When event fully clears for configured duration, re-arm
  |
  +--> On camera disconnect: reconnect with backoff (never stop forever)
  +--> On SMTP error: retry boundedly in background; never block capture
  +--> On crash/reboot: systemd automatically starts application
```

The application must have **one runtime process** when possible, with a capture thread and an inference/send loop or similarly simple robust design. Do not require Redis, Celery, Kubernetes, multi-process APIs, or a queueing service. Small bounded in-memory queues plus a persistent local JSON outbox for emails are acceptable.

## 6. AI black-smoke detection implementation details

### Model loading

- Use `AutoProcessor` and `AutoModelForZeroShotObjectDetection` with `IDEA-Research/grounding-dino-tiny` and current compatible Transformers APIs.
- Use CPU by default, and CUDA automatically if tested/available and explicitly allowed in config.
- Load **once at startup**, apply `torch.inference_mode()`, use eval mode, and warm up on a test frame if feasible.
- Provision/download the model using explicit `python scripts/download_model.py` initially. Store model weights locally for subsequent starts. Production runtime should not depend on fetching from Hugging Face during every boot.
- Document first-run model download size, internet need for setup, local path, and license, and do not make unverified assumptions about inference speed.

### Candidate detection

- Try a short, configurable natural-language description of the target, e.g. `"thick black smoke plume. dark smoke cloud. smoke rising from industrial equipment."`.
- Verify actual model output semantics and thresholds using real implementation, rather than comparing string labels from ordinary COCO YOLO classes.
- Use the supported Grounding DINO processor post-processing APIs to convert boxes into coordinates in the original frame, with box and text thresholds configurable.
- Reject invalid boxes, boxes outside the frame, very small isolated regions if not supportable by sufficient evidence, and anything the model treats as only fire, vehicle, person, etc.

### Black/dark smoke filter — not just a color threshold

- For each smoke candidate bounding box, calculate robust appearance features using OpenCV/NumPy: quantiles of brightness (HSV V or Lab L channel), dark-pixel fraction, variation in texture and (when possible) local contrast against surrounding background.
- **Do NOT simply call `mean_brightness < 100` and assume this is black smoke**. The box might contain a dark machine, building or shadow. Use inner-region/motion-aware analysis and mark results uncertain when foreground/background cannot be separated.
- Prefer comparing temporal changes in the proposed plume region (optical flow/shape changes) across independent frames, while accounting for camera shake, fast shadows and video compression.
- Check that the plume changes shape/moves across frames in a smoke-like way; note still smoke and camera shake limitations.
- Explicitly reject confidently white/light-colored steam or bright-white smoke based on image appearance when evidence is sufficient. Do not use raw model text scores as calibrated probabilities of black smoke.
- Make darkness/motion/score thresholds configurable in `.env`; document that these are **starting heuristics requiring on-site testing**.

### Temporal verification / incident logic

- Sample actual distinct frames at configurable inference FPS (initially 1 FPS for CPU; tune based on measured benchmark).
- Initial rule example: candidate appears in at least **3 distinct frames spanning at least 3 seconds**, shows reasonably consistent smoke-region association, and passes dark-smoke appearance checks before triggering email. These values are tunable starting points, not validated guarantees.
- State machine: `CLEAR -> SUSPECTED -> ALERTED -> CLEARING -> CLEAR`. `SUSPECTED` alone never triggers an email.
- One email per continuously present plume episode. When verified smoke disappears for e.g. 20 seconds, re-arm; a new episode triggers another email.
- When a new verified region appears independently while another remains, optionally treat it as a distinct event; keep implementation small and deterministic for one camera.
- Avoid false duplicate emails after short frame dropouts or camera reconnections. Store minimal `last_alert.json` state atomically (event ID/time + active/resolved state) so a restart during an ongoing event does not flood the mailbox. If reliable continuation state cannot be reconciled after restart, require a fresh verification window before alerting again.
- Store an annotated screenshot and optionally original image only **when an event is verified**, not on every inference frame.

### Performance and 24/7 operation

- Keep the RTSP capture loop running continuously but process only sampled frames; do not claim AI analyzes every input frame.
- A bounded latest-frame buffer must drop stale data rather than build backlog.
- Separate email sending from camera inference so slow SMTP cannot stall detection.
- Track frame age and prevent alerting on stale video frames.
- Resize frames for inference appropriately and correctly map boxes back to full-resolution screenshots.
- Do not promise one-second reaction time before measuring model speed.
- Benchmark CPU usage, RAM, and real inference FPS, and report performance honestly; if unable to keep up, log a degraded warning and recommend better host hardware or reduced inference FPS without pretending it works.

## 7. Email notification requirements

Use **real SMTP**, not Gmail API cloud tooling unless explicitly requested later. Support Gmail SMTP or an existing company SMTP server. No user-account creation screens.

- Use STARTTLS on port 587 or implicit TLS on 465, verify server certificates, and allow SMTP host/port/TLS settings in `.env`.
- Use app password for Gmail **only if the mail account supports it**; an existing company SMTP account is equally valid. No paid third-party email service is required for low-volume alerts, subject to provider sending rules.
- Use `email.message.EmailMessage` with plain-text subject/body and JPEG attachment.
- Example subject: `[BLACK SMOKE ALERT] Dahua Camera 1 - 2026-10-17 22:42 PKT` (derive actual time at runtime, never hardcode date).
- Body: `Possible black smoke detected by camera <camera name> at <local timestamp> (<UTC>). See attached screenshot. This is an AI-generated warning and must be checked according to site safety procedures.`
- Screenshot: filename `black_smoke_YYYYMMDD_HHMMSS_<randomid>.jpg`, annotated bounding rectangle and timestamp (do not expose camera username/password).
- Email one verified NEW episode; do not spam repeated video frames. No white/gray smoke, shadow, person or fire-only messages.
- On SMTP temporary failure, retry with bounded exponential delay without blocking monitoring. Avoid unbounded growth; use small JSON outbox directory or durable JSON manifest plus JPEG reference, and atomic file writes.
- Cap attempts and surface terminal email delivery failure in logs. When SMTP accepts the message, record `accepted_by_smtp`; **do not claim recipient inbox delivery is guaranteed**.
- Provide `python -m smoke_monitor.test_email` to send one clearly marked test message **only when manually run**. It must not send a real smoke alert.
- Do not send any automatic email simply because the app started, stopped, or reconnected.

## 8. Configuration file to generate

Generate `.env.example`, automatically validate required values at app startup, and never commit `.env`.

```dotenv
# One Dahua camera (example address only; replace values)
CAMERA_NAME=Dahua Camera 1
CAMERA_IP=192.168.1.100
CAMERA_RTSP_PORT=554
CAMERA_USERNAME=replace_with_camera_username
CAMERA_PASSWORD=replace_with_camera_password
CAMERA_CHANNEL=1
CAMERA_SUBTYPE=0
# Optional override; leave empty for automatic Dahua URL construction.
CAMERA_RTSP_URL=
CAMERA_RTSP_TRANSPORT=tcp
CAMERA_CONNECT_TIMEOUT_SECONDS=10
CAMERA_STALL_TIMEOUT_SECONDS=10

# Local pretrained detection, NO training
MODEL_ID=IDEA-Research/grounding-dino-tiny
MODEL_LOCAL_DIR=./models/grounding-dino-tiny
DEVICE=cpu
INFERENCE_FPS=1
MODEL_BOX_THRESHOLD=0.30
MODEL_TEXT_THRESHOLD=0.25
DARK_PIXEL_LUMINANCE_THRESHOLD=90
MIN_DARK_PIXEL_FRACTION=0.40
MIN_TEMPORAL_DETECTIONS=3
MIN_DETECTION_SPAN_SECONDS=3
EVENT_CLEAR_SECONDS=20

# SMTP for sending screenshot emails (example values only)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USERNAME=replace_with_email@example.com
SMTP_PASSWORD=replace_with_app_password_or_smtp_password
SMTP_FROM=replace_with_email@example.com
ALERT_EMAIL_TO=recipient@example.com
SMTP_TIMEOUT_SECONDS=20
EMAIL_RETRY_LIMIT=5

# Local file/operational settings
TIMEZONE=Asia/Karachi
DATA_DIR=./data
SCREENSHOT_KEEP_DAYS=30
LOG_LEVEL=INFO
```

**IMPORTANT:** All threshold numbers are initial tunable *heuristics*, not tested settings. The model may not recognize black smoke at all in a given scene. In that case, the agent must report the failure, collect evaluation evidence, and suggest an alternative permissively licensed pretrained inference model rather than pretend results work.

If separate camera credentials are assembled into a URL, percent-encode them properly and avoid recording resulting URL in exception tracebacks/logs. `.env` permissions must be restricted to the machine/service account.

## 9. Required lightweight project structure

Build this structure (minor justified adjustments allowed):

```text
black-smoke-monitor/
├── README.md                       # requirements and exact setup/run instructions
├── .env.example                    # camera, detector, SMTP settings
├── .gitignore                      # ignore .env, secrets, logs, snapshots, model cache
├── requirements.txt                # pinned compatible package versions
├── THIRD_PARTY_LICENSES.md         # model + dependency license notices
├── smoke_monitor/
│   ├── __init__.py
│   ├── __main__.py                  # entry: python -m smoke_monitor
│   ├── config.py                    # parse/validate .env
│   ├── camera.py                    # Dahua RTSP reader, reconnect, latest-frame buffer
│   ├── detector.py                  # pretrained Grounding DINO inference
│   ├── verifier.py                  # dark-smoke heuristic + temporal episode logic
│   ├── screenshot.py                # annotated JPEG and timestamp
│   ├── email_alert.py               # SMTP sender and retry/outbox
│   ├── state.py                     # incident/re-arm/restart state
│   ├── monitor.py                   # orchestrates 24/7 process
│   ├── log_setup.py                 # rotating logs, credential redaction
│   └── test_email.py                # manually invoked email test
├── scripts/
│   ├── download_model.py           # one-time download + revision/license log
│   ├── test_camera.py              # verify RTSP and decode frames
│   ├── benchmark.py                # measure actual inference rate/host resource use
│   └── replay_video.py             # offline detection test with a file
├── tests/
│   ├── test_config.py
│   ├── test_camera_reconnect.py
│   ├── test_dark_smoke_rules.py
│   ├── test_episode_deduplication.py
│   ├── test_email_retry.py
│   └── test_replay_flow.py
├── deploy/
│   └── black-smoke-monitor.service # Ubuntu systemd service
├── models/                          # downloaded pretrained weights (gitignored)
└── data/
    ├── screenshots/                 # JPEG evidence only for triggered events
    ├── email_outbox/                # pending emails for retries
    ├── logs/                        # rotated diagnostic logs
    └── state/                       # minimal incident state (JSON)
```

No database, dashboard, external queue, REST API, or login component. Don't create empty modules just to match this list: each file must implement something real.

## 10. Operating system / deployment

Primary deployment: **Ubuntu Linux on an always-on computer/mini PC** connected to the same local network as the Dahua camera, with an internet path (or company SMTP relay) for email.

Provide exact executable steps in the README:

1. Install Python, FFmpeg, OS dependencies and requirements.
2. Copy `.env.example` to `.env`, set actual Dahua details and SMTP credentials; restrict permissions.
3. Run `python scripts/test_camera.py` and verify a fresh frame decodes.
4. Run `python scripts/download_model.py` once and verify it loads from disk.
5. Run `python scripts/benchmark.py` on the host.
6. Run `python -m smoke_monitor.test_email` only when user explicitly chooses to verify SMTP.
7. Run `python -m smoke_monitor` manually in foreground first, and observe status logs.
8. Install/enable `deploy/black-smoke-monitor.service` with `systemd`, `Restart=always`, bounded restart delay and working directory/environment correctly set.
9. Verify `systemctl status`, `journalctl -u black-smoke-monitor -f`, `systemctl restart`, stopping safely and power-on auto-start.
10. Document log and screenshot retention, and what to check when camera or SMTP goes offline.

Do not open a local web port or expose RTSP outside the company LAN. The process should run with a dedicated restricted OS service account, not root, and with only needed directory permissions.

If the user develops on macOS, include local commands that work there; Ubuntu `systemd` deployment is the production path. Docker is NOT required and should not be introduced unless truly necessary.

## 11. Detailed reliability and error-handling requirements

- Startup config errors: fail fast with a clear sanitized message identifying the missing variable, not a Python stack trace with secrets.
- Model setup: no silent fallback to fake detections or cloud API.
- Capture: reconnect with exponential backoff, release decoder resources, enforce timeouts, no unbounded CPU loops, do not repeatedly restart model on transient camera errors.
- When camera goes offline: set local state to unavailable, log status, keep retrying; never send a “no smoke” email and never claim camera monitoring is healthy while no frames are arriving.
- Inference error: log concise traceback with redacted secrets, retry cautiously, and flag degraded state in logs; don't process unbounded stale frames.
- Screenshots: write atomic image files, safe names, no filesystem traversal, keep only real-event evidence, apply 30-day retention by default; configurable.
- SMTP: timeout, bounded retries and durable unsent messages, log provider acceptance not delivery confirmation, no recursive alert floods.
- Crash/reboot: systemd restarts the process; state/outbox survive; no immediate duplicate alert if same plume persists after restart.
- Signals: gracefully handle SIGINT/SIGTERM, close OpenCV/FFmpeg, flush local state and stop background workers.
- Logs: rotate, no plaintext passwords, no actual RTSP URL with password, concise periodic health log containing frame age, inference time, active incident state and pending email count.
- Resource use: do not accumulate frames/screenshots in RAM. Use backpressure, bounded queues and configurable inference FPS.
- `camera_status`, `last_frame_age`, `last_inference_age` are only log metrics; no dashboard needed.

## 12. Tests that MUST exist

### Unit tests (all without a live camera or SMTP)

- Parse Dahua main URL and substitute correct channel/subtype; safely escape credentials, ensure redaction in logs.
- Verify candidate bounding boxes are mapped to original frame coordinates; clip out-of-bounds boxes.
- Verify dark-smoke heuristic outputs are sensible for synthetic bright/dark/masked regions; demonstrate that darkness alone is insufficient.
- Verify temporal thresholds; no email after only one ambiguous frame.
- Verify white smoke or bright steam candidate does **not** satisfy dark-smoke rules in representative labeled fixtures.
- Verify dark static object candidate does **not** satisfy smoke-like motion/temporal confirmation in deterministic fixtures.
- Verify a new verified smoke episode triggers **one** mail; persistent frames do not trigger duplicates; clear + return triggers a new email.
- Verify recovery after stream timeouts/reconnects, stale-frame detection, safe shutdown.
- Verify screenshot exists and includes a timestamp/annotation; verify no screenshot is created for ordinary frames.
- Verify retry queue survives process restart, errors are bounded, email attachment bytes are correct and no real mail sent in CI.

### Integration / offline replay

- `python scripts/replay_video.py --video path/to/clip.mp4` runs **the real pretrained model** (when locally provisioned) and emits a JSON summary including candidates, accepted/rejected decisions, screenshots created and any alert events with sending disabled.
- Include a `--dry-run-email` mode to test incident-email composition without sending.
- Provide a deterministic **test-only detector stub** to verify the end-to-end email flow, clearly marked as test-only; NEVER use it silently in production.
- Benchmarks give measured inference FPS/latency/RAM/CPU usage from the actual host, or say “not measured” when unavailable.
- Real field footage should be manually reviewed; provide a test checklist for black smoke vs dark object, shadow, steam, cloud, dusk/night and rain. Do not state accuracy without reference-label results.

## 13. Definition of done / acceptance checks

- [ ] No sign-up/login/dashboard/API/database exists.
- [ ] The app runs from a single command: `python -m smoke_monitor`.
- [ ] Configurable Dahua RTSP main stream connects and decodes real fresh frames (after user provides correct IP and credentials).
- [ ] A **real downloaded pretrained model** is loaded and used, not fake detection code.
- [ ] Frames are continually captured and sampled, and potential smoke candidates go through dark appearance and temporal verification.
- [ ] Only a qualifying **suspected black-smoke event** triggers an alert; the software doesn't alert for unrelated model labels or solely a shadow's darkness.
- [ ] Alert includes actual annotated screenshot from a real camera frame and correct runtime timestamp.
- [ ] One mail per continuous episode; new smoke after clearing generates a new mail.
- [ ] SMTP attempts/retries do not block camera processing; actual server acceptance is recorded honestly.
- [ ] Camera disconnects recover automatically; monitoring restarts after reboot/crash on Ubuntu.
- [ ] Model and code dependency licenses/revisions are recorded; no paid services or custom training are needed.
- [ ] Sensitive values are not committed/logged; evidence/logs have retention.
- [ ] Unit tests and offline replay run; all test results are reported truthfully.
- [ ] README includes setup, troubleshooting, camera RTSP check, SMTP test, systemd install and common commands.

## 14. Implementation order — don't stop at planning

**Step A.** Create runnable Python project, packages, `.env.example`, `.gitignore`, requirements and README. Validate environment variables.

**Step B.** Implement Dahua RTSP connection, fresh frame access, reconnect and camera-test script. Make it work with an offline video replay source too.

**Step C.** Implement official Grounding DINO Tiny pretrained model download and inference adapter; smoke-region localization and output format. Run benchmark and log real results.

**Step D.** Implement conservative black/dark-smoke appearance checks, temporal verification, event state, clearing/rearm, evidence screenshot creation, and tests.

**Step E.** Implement real SMTP screenshot alert, durable retry folder, test email CLI, and email-related tests.

**Step F.** Integrate capture → inference → verification → save screenshot → send email → keep running. Add operational logs and failure recovery.

**Step G.** Add production Ubuntu systemd service, setup/troubleshooting, full test suite, model/license manifest, and field-validation checklist.

For **every step**, write actual working files and commands, run tests where the environment allows, and transparently disclose anything blocked by missing hardware, SMTP credentials, unavailable model files or untested detection accuracy. Do not invent test results. Proceed without unnecessary clarification: use clearly documented placeholders in `.env.example` until the operator configures them.

## 15. Final output expected from you (coding agent)

Deliver one complete source folder with all necessary Python code, config template, executable CLI commands, tests and `systemd` service. Give a concise setup walkthrough:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in Dahua RTSP and SMTP configuration in .env.
python scripts/test_camera.py
python scripts/download_model.py
python scripts/benchmark.py
python -m smoke_monitor.test_email   # Only when ready to send a test message
python -m smoke_monitor
```

Then show production `systemd` commands and exact commands to view logs. Confirm plainly which parts were *actually tested*, which require access to the actual Dahua camera and SMTP account, and whether **black-smoke-only accuracy** has been field-validated.

**Remember the user wants ONLY:** Dahua IP camera → continuous monitoring → detect suspected black smoke → screenshot → email → continue monitoring. **Nothing else.**
