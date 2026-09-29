#!/bin/zsh
# Install (or reinstall) the launchd job that runs the local, read-only dashboard (dashboard/) at login and
# keeps it running, from the checkout this script is in, at http://127.0.0.1:8787/ (this Mac only).
# The dashboard reads the ledgers, run records, STATUS.md and launchd's job status; it writes nothing the
# jobs own and places no bet. Remove it with ops/uninstall_dashboard.sh.
#   ops/install_dashboard.sh                 install / reinstall
#   ops/install_dashboard.sh --print-plist   print the job file it would write, and change nothing
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.valuefinder.dashboard"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/value-finder-dashboard.log"
PORT=8787
PY="$ROOT/dashboard/.venv/bin/python"
plist() {
cat <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>$PY</string><string>-m</string><string>vfdash</string>
    <string>--port</string><string>$PORT</string><string>--root</string><string>$ROOT</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT/dashboard</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
PLIST
}
if [[ "${1:-}" == "--print-plist" ]]; then plist; exit 0; fi
UV="$(command -v uv || true)"
if [[ -z "$UV" ]]; then echo "uv is not installed (brew install uv), so the dashboard's Python can't be set up"; exit 1; fi
# the dashboard's own environment (standard library only; pytest is left out here)
"$UV" sync --project "$ROOT/dashboard" --frozen --no-dev --quiet
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
# a second copy on the same port would stop at once and be restarted every 30 seconds: check the port first
for try in {1..10}; do
  [[ -z "$(/usr/sbin/lsof -nP -iTCP:$PORT -sTCP:LISTEN -t 2>/dev/null || true)" ]] && break
  sleep 0.5
done
if [[ -n "$(/usr/sbin/lsof -nP -iTCP:$PORT -sTCP:LISTEN -t 2>/dev/null || true)" ]]; then
  echo "Port $PORT is already in use on this Mac (perhaps a copy of the dashboard started by hand or from the"
  echo "preview), so nothing was installed. Stop that copy and run this script again."
  exit 1
fi
plist > "$PLIST"
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "installed $LABEL -> $PLIST (log: ~/Library/Logs/value-finder-dashboard.log)"
echo "Open http://127.0.0.1:$PORT/ in Safari. To put it in the Dock: in Safari, File > Add to Dock."
