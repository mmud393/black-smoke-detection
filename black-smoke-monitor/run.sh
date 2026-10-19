#!/usr/bin/env bash
# One command: creates the venv and installs dependencies if needed, then starts the monitor.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
exec .venv/bin/python main.py
