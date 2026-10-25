#!/usr/bin/env bash
# One-command local setup + run (no Docker): backend :8000, H-MEM sidecar :8765, frontend :5174.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[ -f .env ] || cp .env.example .env
if [ ! -d backend/.venv ]; then
  if command -v uv >/dev/null; then uv venv -q --python 3.12 backend/.venv || uv venv -q backend/.venv; uv pip install -q -e "backend[dev]" --python backend/.venv/bin/python
  else python3 -m venv backend/.venv && backend/.venv/bin/pip install -q -e "backend[dev]"; fi
fi
[ -d services/hmem-sidecar/node_modules ] || (cd services/hmem-sidecar && npm install --no-audit --no-fund)
[ -d services/hmem-sidecar/vendor/hmem ] || (cd services/hmem-sidecar && npm run setup)
[ -d frontend-v2/node_modules ] || (cd frontend-v2 && npm install --no-audit --no-fund)
trap 'kill 0' EXIT
(cd services/hmem-sidecar && npm start) &
(cd backend && .venv/bin/uvicorn app.main:app --port 8000) &
(cd frontend-v2 && npm run dev -- --host 127.0.0.1) &
wait
