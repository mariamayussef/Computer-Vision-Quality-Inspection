#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  echo 'Create the Python 3.12 virtual environment and install requirements.lock first. See README.md.'
  exit 1
fi
.venv/bin/python scripts/manage.py migrate
if [ -f "${MODEL_DIR:-models/bottle-v1}/config.json" ]; then
  .venv/bin/python scripts/manage.py register-model
fi
if ! .venv/bin/python -c "from backend.app.db import Session,User; from sqlalchemy import select; db=Session(); raise SystemExit(0 if db.scalar(select(User).where(User.role=='admin')) else 1)"; then
  read -r -p 'Choose your administrator username: ' inspection_admin_name
  .venv/bin/python scripts/manage.py user "$inspection_admin_name" --role admin
fi
if [ ! -d frontend/dist ]; then
  echo 'Build the frontend with: cd frontend && pnpm install --frozen-lockfile && pnpm build'
  exit 1
fi
echo 'Open http://127.0.0.1:8000 — press Ctrl+C to stop.'
exec .venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
