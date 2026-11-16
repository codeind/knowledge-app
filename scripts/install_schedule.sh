#!/usr/bin/env bash
# Installs a macOS launchd job that runs scripts/daily_pipeline.sh every day at 06:17 (when the Mac is awake;
# if it was asleep, launchd runs it once when it wakes).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.knowledge.daily-pipeline"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/backend/logs"
chmod +x "$ROOT/scripts/daily_pipeline.sh"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$ROOT/scripts/daily_pipeline.sh</string></array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>17</integer></dict>
  <key>StandardOutPath</key><string>$ROOT/backend/logs/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$ROOT/backend/logs/launchd.err.log</string>
</dict>
</plist>
PLIST
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Installed: runs daily at 06:17. Test now with: launchctl start $LABEL"
echo "Logs: $ROOT/backend/logs/"
