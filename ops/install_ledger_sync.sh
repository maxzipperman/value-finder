#!/bin/zsh
# Install (or remove) the launchd job that runs ops/sync_ledgers.sh daily at 23:45,
# after the last alert run of the day.
#   ops/install_ledger_sync.sh           install / reinstall
#   ops/install_ledger_sync.sh --remove  uninstall
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.valuefinder.ledgersync"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if [[ "${1:-}" == "--remove" ]]; then rm -f "$PLIST"; echo "removed $LABEL"; exit 0; fi
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string><string>$ROOT/ops/sync_ledgers.sh</string>
  </array>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>23</integer><key>Minute</key><integer>45</integer></dict>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/valuefinder-ledgersync.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/valuefinder-ledgersync.log</string>
</dict></plist>
PLIST
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "installed $LABEL -> $PLIST (log: ~/Library/Logs/valuefinder-ledgersync.log)"
