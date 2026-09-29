#!/bin/zsh
# Install (or remove) the launchd job that runs ops/capture_closes.sh every 15 minutes.
# The Mac has to be awake at kickoff for a close to be captured; missed slots are
# reported as missing by score_forward.py.
#   ops/install_close_capture.sh           install / reinstall
#   ops/install_close_capture.sh --remove  uninstall
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.valuefinder.closecapture"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if [[ "${1:-}" == "--remove" ]]; then rm -f "$PLIST"; echo "removed $LABEL"; exit 0; fi
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string><string>$ROOT/ops/capture_closes.sh</string>
  </array>
  <key>StartInterval</key><integer>900</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/valuefinder-closecapture.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/valuefinder-closecapture.log</string>
</dict></plist>
PLIST
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "installed $LABEL -> $PLIST (log: ~/Library/Logs/valuefinder-closecapture.log)"
