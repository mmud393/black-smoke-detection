# Black Smoke Monitor

Spec: [BLACK_SMOKE_CLAUDE_CODE_PROMPT.md](BLACK_SMOKE_CLAUDE_CODE_PROMPT.md) (watch RTSP camera -> detect black smoke -> screenshot -> email).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# edit .env: RTSP_URL, then SMTP_* and EMAIL_ENABLED=true after verifying
./run.sh
pytest
```

- All settings come from `.env` via `config.py`. Missing template keys are reported at startup.
- The ONNX model (pyronear/yolo11s_sensitive-detector) is downloaded to `models/` on first run (needs internet once). Its ONNX metadata says AGPL-3.0 while the model card says Apache-2.0: confirm licensing before company use.
- `EMAIL_ENABLED=false` never contacts SMTP; screenshots are still saved to `screenshots/`.
- Limitations: not a certified fire alarm; thresholds (`BLACK_LUMA_MAX`, `BLACK_DARK_PIXEL_RATIO_MIN`, motion) must be tuned on real footage.
- `legacy/` holds the previous implementation (motion detector + Claude confirmation) for reference.
