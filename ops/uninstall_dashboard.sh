#!/bin/zsh
# Remove the launchd job that runs the local dashboard (installed by ops/install_dashboard.sh). It stops the
# dashboard and deletes only its own job file; the dashboard's code, the ledgers and the other jobs are untouched.
#   ops/uninstall_dashboard.sh
set -euo pipefail
LABEL="com.valuefinder.dashboard"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$PLIST"
echo "removed $LABEL (a Dock icon added from Safari can be dragged out of the Dock)"
