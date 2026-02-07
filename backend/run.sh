#!/usr/bin/env bash
# Run the backend for local dev. Use this from the project root or from backend/.
# Ensures we run from backend/ with the venv so /api/locations and other routes work.

set -e
cd "$(dirname "$0")"

if [[ ! -d .venv ]]; then
  echo "No .venv found. Create one and install deps:"
  echo "  python -m venv .venv"
  echo "  .venv/bin/pip install -r requirements.txt"
  exit 1
fi

echo "Starting backend at http://127.0.0.1:8001 (API at /api/health, /api/locations)"
exec .venv/bin/python -m uvicorn main:app --reload --host 0.0.0.0 --port 8001
