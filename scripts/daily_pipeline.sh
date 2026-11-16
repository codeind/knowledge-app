#!/usr/bin/env bash
# Runs the daily content job (news + new US rules + relink). Called by the schedule; safe to run by hand.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
mkdir -p logs
LOG="logs/daily-$(date +%Y-%m-%d).log"
{
  echo "=== $(date) ==="
  if [ ! -x .venv/bin/python ]; then
    echo "No .venv yet: run ./start.sh once first."; exit 1
  fi
  .venv/bin/python -m kb.cli run daily
  .venv/bin/python -m kb.cli stats
} >> "$LOG" 2>&1
