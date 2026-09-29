#!/usr/bin/env bash
# Log live prices for NFL and CFB games with an active Rule B wind trigger (logging only).
# Runs every 10 minutes from launchd (ops/install_live_uses.sh). Costs 1 Odds API credit per
# sport per run with a trigger, nothing otherwise, and nothing at all on the free plan.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export ODDS_QUOTA_KIND="${ODDS_QUOTA_KIND:-background}"
(cd "$ROOT/nfl-weather" && .venv/bin/python scripts/poll_triggers.py)
(cd "$ROOT/cfb-weather" && .venv/bin/python scripts/poll_triggers.py)
exit 0
