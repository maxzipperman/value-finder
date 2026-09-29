#!/usr/bin/env bash
# Record the closing total for any NFL or CFB kickoff slot starting in 2-20 minutes
# (nfl-weather amendment 3, cfb-weather amendment 2). Runs every 15 minutes from
# launchd (ops/install_close_capture.sh). Costs 1 Odds API credit per sport per
# kickoff slot, and nothing when no game is about to start. Both sports always run;
# the exit code is non-zero if either failed, and the failure is in the log.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
rc=0
(cd "$ROOT/nfl-weather" && .venv/bin/python scripts/capture_close.py) || { rc=1; echo "$(date -u +%FT%TZ) NFL close capture failed"; }
(cd "$ROOT/cfb-weather" && .venv/bin/python scripts/capture_close.py) || { rc=1; echo "$(date -u +%FT%TZ) CFB close capture failed"; }
exit $rc
