#!/usr/bin/env bash
# Rebuild the website and copy it into backend/site so the Python server can serve it.
# Run this after changing anything in web/ (needs Node.js).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/web"
[ -d node_modules ] || npm install --silent
npm run build
rm -rf "$ROOT/backend/site"
cp -R out "$ROOT/backend/site"
echo "Website rebuilt into backend/site"
