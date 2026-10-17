# Architecture

Black Smoke Monitor is a **supplemental** on-premises monitoring aid for suspected black smoke. It is not a certified fire alarm.

## Layout (Step 01)

```
shared/    installable package `smoke_shared`: typed config, redacted JSON logging, enums
           (later: SQLAlchemy models + Pydantic contracts used by BOTH services)
backend/   FastAPI service, package `app`  (run: python -m app, cwd backend/)
worker/    monitoring worker, package `smoke_worker` (run: python -m smoke_worker)
frontend/  React + TypeScript + Vite + Tailwind
scripts/ deploy/ fixtures/ data/ docs/
```

### Deviation from the master specification (documented per prompt rules)
The master tree puts models and config under `backend/app/`. Because the API and worker are separate processes that must share DB models and configuration, those live in the installable `shared/` package. Neither service imports the other's entrypoint: `app` and `smoke_worker` each depend only on `smoke_shared`. The worker also has its own `worker/pyproject.toml` so heavy inference dependencies (torch, transformers, OpenCV) can be added as an extra later without bloating the API image.

## Processes
- **API**: HTTP only. Never captures video or runs inference.
- **Worker**: separate OS process. In Step 01 it only starts, logs `IDLE_NOT_MONITORING` and exits cleanly on SIGINT/SIGTERM.
- **Frontend**: browser talks only to same-origin `/api` and `/health` (Vite proxy in dev).

## Cross-cutting behaviour implemented now
- Config: `smoke_shared.config.Settings` (env / `.env`); invalid config exits with code 2 and a readable message. Production refuses a placeholder/short `APP_SECRET_KEY`, insecure cookies, and exposed API docs.
- Logging: one JSON line per event, `request_id` correlation, URL credentials and sensitive keys redacted (`smoke_shared.redaction`). Query strings are not logged.
- Errors: `{"error": {"code", "message", "request_id", "details?"}}`; validation details contain field locations, never submitted values; 500s never leak internals.
- Health: `GET /health/live` is liveness only. `GET /health/ready` returns **503 NOT_READY** with database/worker/model reported as `NOT_CONFIGURED`/`UNKNOWN` until later steps implement them.
