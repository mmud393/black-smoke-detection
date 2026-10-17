PY ?= python3.12
VENV = .venv
BIN = $(VENV)/bin

.PHONY: install install-frontend api worker frontend test lint typecheck build lock

install:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -r requirements-lock.txt
	$(BIN)/pip install --no-deps -e shared -e backend -e worker

install-frontend:
	cd frontend && npm ci

api:
	cd backend && ../$(BIN)/python -m app

worker:
	$(BIN)/python -m smoke_worker

frontend:
	cd frontend && npm run dev

test:
	$(BIN)/pytest -q shared backend worker

lint:
	$(BIN)/ruff check backend shared worker
	cd frontend && npm run lint

typecheck:
	cd frontend && npm run typecheck

build:
	cd frontend && npm run build

# Regenerate the lockfile from a clean venv after changing dependencies.
lock:
	$(BIN)/pip freeze --exclude-editable > requirements-lock.txt
