#!/usr/bin/env bash
# One command: ./run.sh  -> setup if needed, then start the monitor.
set -e
cd "$(dirname "$0")"

if [ -d .venv ]; then VENV=.venv; elif [ -d ../.venv ]; then VENV=../.venv
else python3 -m venv .venv && VENV=.venv && .venv/bin/pip install -r requirements.txt; fi
PY="$VENV/bin/python"

if [ ! -f .env ]; then
  cp .env.example .env && chmod 600 .env
  echo "Created .env - fill in camera + SMTP + ANTHROPIC_API_KEY values, then run ./run.sh again."; exit 1
fi

exec "$PY" -m smoke_monitor
