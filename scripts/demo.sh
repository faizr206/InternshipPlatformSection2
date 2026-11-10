#!/usr/bin/env bash
# Start the P04/P05 demo and share it through ngrok.
#
#   scripts/demo.sh            # run tests, start the app, open the ngrok tunnel
#   scripts/demo.sh --reset    # same, but start from fresh demo data (deletes app.db)
#   scripts/demo.sh --local    # no ngrok, just the app on http://127.0.0.1:8000
#
# Settings (environment variables):
#   PORT          local port (default 8000)
#   NGROK_DOMAIN  your ngrok static domain (default: the one on the Sprint 1 slides)
#   SKIP_TESTS=1  skip the test run before starting
#
# Ctrl+C stops both ngrok and the app.
set -euo pipefail

cd "$(dirname "$0")/.."

PORT="${PORT:-8000}"
NGROK_DOMAIN="${NGROK_DOMAIN:-theodore-nonextended-rocio.ngrok-free.dev}"
RESET=0
LOCAL=0
for arg in "$@"; do
  case "$arg" in
    --reset) RESET=1 ;;
    --local) LOCAL=1 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

need() { command -v "$1" >/dev/null || { echo "Missing '$1'. $2" >&2; exit 1; }; }
need uv "Install it: https://docs.astral.sh/uv/"
if [ "$LOCAL" -eq 0 ]; then
  need ngrok "Install it: brew install ngrok"
  ngrok config check >/dev/null 2>&1 || {
    echo "ngrok is not set up. Run: ngrok config add-authtoken <your token>" >&2; exit 1; }
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $PORT is already in use. Stop that process or run with PORT=8001." >&2
  exit 1
fi

echo "==> Installing dependencies"
uv sync --quiet

if [ "${SKIP_TESTS:-0}" != "1" ]; then
  echo "==> Running tests"
  uv run pytest -q
fi

if [ "$RESET" -eq 1 ]; then
  echo "==> Resetting demo data (deleting app.db)"
  rm -f app.db
fi

echo "==> Starting the app on http://127.0.0.1:$PORT"
uv run uvicorn app.main:app --host 127.0.0.1 --port "$PORT" &
APP_PID=$!
cleanup() { kill "$APP_PID" 2>/dev/null || true; wait "$APP_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

for _ in $(seq 1 40); do
  curl -fs "http://127.0.0.1:$PORT/api/skills" >/dev/null && break
  kill -0 "$APP_PID" 2>/dev/null || { echo "The app failed to start." >&2; exit 1; }
  sleep 0.25
done
curl -fs "http://127.0.0.1:$PORT/api/skills" >/dev/null || { echo "The app did not answer in time." >&2; exit 1; }

if [ "$LOCAL" -eq 1 ]; then
  echo "==> Ready: http://127.0.0.1:$PORT  (Ctrl+C to stop)"
  wait "$APP_PID"
else
  echo "==> Public link: https://$NGROK_DOMAIN  (Ctrl+C to stop)"
  ngrok http --url="https://$NGROK_DOMAIN" "$PORT"
fi
