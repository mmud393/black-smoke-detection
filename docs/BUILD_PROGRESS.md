# Build Progress

| Step | State |
|---|---|
| 01 Foundation | IMPLEMENTED — VERIFIED for the items listed below (see Not verified) |
| 02–12 | NOT_STARTED |

## Step 01 — Repository, configuration and runnable foundation

**Capabilities:** monorepo skeleton; `smoke_shared` (config, redaction, JSON logging, enums); FastAPI app with request IDs, error envelope, CORS, `/health/live`, `/health/ready` (always 503 NOT_READY for now); idle worker with signal-driven shutdown; Vite React TS shell with routing, TanStack Query, live API indicator, System Health page; other screens say "Not implemented yet".

**Key files:** `shared/smoke_shared/{config,logging,redaction,enums}.py`, `backend/app/{main,errors,middleware,__main__}.py`, `backend/app/api/health.py`, `worker/smoke_worker/main.py`, `frontend/src/**`, `Makefile`, `.env.example`, `requirements-lock.txt`.

**Versions:** Python 3.12.8 (supports 3.11–3.12). Node 18.17.0 used locally; `package.json` engines says >=18.18 (ESLint 9 asks for it; it still ran on 18.17 with EBADENGINE warnings). Vite 5 and Tailwind 3 chosen to stay compatible with Node 18. Locked Python versions: `requirements-lock.txt` (pip freeze); frontend: `package-lock.json`.

**Commands run and results (2026-10-17):**
- `pytest -q shared backend worker` → 9 passed
- `ruff check backend shared worker` → clean
- `cd frontend && npm run typecheck` → ok; `npm run lint` → exit 0; `npm run build` → built
- Fresh venv from `requirements-lock.txt` + editable installs → 9 passed
- `python -m app` + `curl /health/live` → 200; `/health/ready` → 503 NOT_READY; same `/health/live` through Vite dev proxy (:5173) → 200
- `APP_ENV=production python -m app` (placeholder secret) → exit 2 with readable message

**Not verified:** browser-rendered UI (no visual check done; only build/typecheck/lint and proxy request); Docker (not part of this step); Node >=18.18 behaviour.

**Known limitations:** no database, auth, cameras, model, email. `/health/ready` cannot become ready until Step 02+ . Dev-only HTTP.

**Contracts so far:** error envelope above; health responses `{status:"alive",time}` and `{status, components{api,database,worker,model}, detail}`; env vars in `.env.example`.

**Next step:** 02 (database, migrations, shared contracts) can begin.
