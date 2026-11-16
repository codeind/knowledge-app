#!/usr/bin/env bash
# One-command local start.
# - With Node.js: API on :8000 and the live-reloading web app on :3000 (for editing the front end).
# - Without Node.js: the API also serves the pre-built website, so everything is on http://localhost:8000.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is not installed. Install Python 3.11+ from https://www.python.org/downloads/"
  exit 1
fi

cd "$ROOT/backend"
if [ ! -d .venv ]; then
  echo "Setting up Python environment..."
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
fi
[ -f .env ] || cp .env.example .env
.venv/bin/python -m kb.cli seed > /dev/null

if ! command -v npm >/dev/null 2>&1 || [ "${1:-}" = "--python-only" ]; then
  echo "Starting the app at http://localhost:8000  (Python only; press Ctrl+C to stop)"
  echo "To edit the website itself, install Node.js 20+ from https://nodejs.org and run ./start.sh again."
  exec .venv/bin/uvicorn kb.api:app --port 8000
fi

echo "API on http://localhost:8000 (docs at /docs)"
.venv/bin/uvicorn kb.api:app --port 8000 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT

cd "$ROOT/web"
if [ ! -d node_modules ]; then
  echo "Installing web dependencies..."
  npm install --silent
fi
echo "Web app on http://localhost:3000"
npm run dev
