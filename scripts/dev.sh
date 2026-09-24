#!/usr/bin/env bash
# Start NEXUS for development: FastAPI backend on :8000 and the Vite dev server on :5173.
# First run installs dependencies. Stop with Ctrl+C.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -x "$ROOT/backend/.venv/bin/python" ]; then
  echo "▸ Creating Python environment…"
  python3 -m venv "$ROOT/backend/.venv"
  "$ROOT/backend/.venv/bin/pip" install -q --upgrade pip
  "$ROOT/backend/.venv/bin/pip" install -q -e "$ROOT/backend[dev]"
fi
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "▸ Installing frontend packages…"
  (cd "$ROOT/frontend" && npm install --no-audit --no-fund)
fi

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "▸ Backend  → http://127.0.0.1:8000 (API docs at /api/docs)"
(cd "$ROOT/backend" && exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload) &
echo "▸ Frontend → http://localhost:5173"
(cd "$ROOT/frontend" && exec npm run dev -- --host 127.0.0.1) &
wait
