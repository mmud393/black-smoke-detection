# Black Smoke Monitor

On-premises monitoring aid that will read IP-camera streams, flag **suspected** black smoke with a pretrained model, keep evidence and send email alerts. **Not a certified fire alarm and not a substitute for approved detectors or site safety procedures.**

**Status: build step 01 of 12 — foundation only.** No detection, cameras, email or database yet. See [docs/BUILD_PROGRESS.md](docs/BUILD_PROGRESS.md).

## Requirements
Python 3.11 or 3.12 · Node >=18.18 (local run used 18.17) · no GPU needed for this step.

## Setup
```
cp .env.example .env
make install            # venv from requirements-lock.txt + editable shared/backend/worker
make install-frontend
```
## Run (three terminals)
```
make api        # http://127.0.0.1:8000/health/live
make worker     # idle; Ctrl+C to stop
make frontend   # http://localhost:5173 (proxies /api and /health to the API)
```
Set `EXPOSE_API_DOCS=true` in development to enable `/api/docs`.

## Check
`make test lint typecheck build` — see [docs/TESTING.md](docs/TESTING.md).

## Secrets
`.env`, runtime data, model weights and evidence are git-ignored. Use placeholders in `.env.example` only.
