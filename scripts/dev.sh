#!/usr/bin/env bash
# Run the backend API (port 8000) and, if present, the Vite dev server (port 5173) together.
# Ctrl+C stops both. Use --reset to start from fresh demo data.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ "${1:-}" == "--reset" ]]; then rm -f "$ROOT/backend/app.db"; fi

(cd "$ROOT/backend" && uv sync -q && uv run uvicorn app.main:app --reload --port "${PORT:-8000}") &
API_PID=$!
trap 'kill $API_PID ${WEB_PID:-} 2>/dev/null || true' EXIT INT TERM

if [[ -f "$ROOT/frontend/package.json" ]]; then
  (cd "$ROOT/frontend" && { [[ -d node_modules ]] || npm install; } && npm run dev) &
  WEB_PID=$!
fi
wait
