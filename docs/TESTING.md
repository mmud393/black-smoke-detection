# Testing

```
make test        # pytest: shared, backend, worker
make lint        # ruff + eslint
make typecheck   # tsc --noEmit
make build       # vite production build
```
Current coverage (Step 01): config validation, redaction, health endpoints, error envelope/request IDs, worker start/stop on SIGTERM and bad-config exit code. No tests exist yet for cameras, detection, email or UI behaviour; real-camera, GPU, model and SMTP validation are NOT RUN.
