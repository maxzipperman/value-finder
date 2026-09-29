#!/bin/sh
# The whole GFS MOS pull for issue #40: CFB 2023-25 first (the validation sample), then CFB
# 2006-25, then NFL 2004-25. Cache-first: a rerun skips every window already downloaded, so this
# is also the command that finishes an interrupted pull. Free (Iowa Environmental Mesonet), no key.
# Keeps the Mac awake while it runs (caffeinate -i ends with it) and logs to the shared cache.
#
#   nohup cfb-weather/scripts/mos_pull_all.sh > ~/.cache/value-finder/mos/fetch_full.log 2>&1 &
#
# Start it from a checkout that will outlive the run (about 2,600 requests, 5+ hours), not from a
# worker's worktree: the worktree is removed when the worker is archived, and the later legs cd
# into it. A leg whose folder is gone stops the script instead of running in the wrong place.
#
# Each leg is a new process, and the pacing inside mos.py starts fresh in each one, so a leg
# that opened right after the last one's final request drew an HTTP 429 (and a slower pace for
# the rest of that leg). PAUSE_S seconds before every leg, including the first (a restart right
# after a stopped run), avoids that.
#
# Each project's Python defaults to its own .venv; set PY_CFB / PY_NFL to use another.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY_CFB="${PY_CFB:-$ROOT/cfb-weather/.venv/bin/python}"
PY_NFL="${PY_NFL:-$ROOT/nfl-weather/.venv/bin/python}"
PAUSE_S="${PAUSE_S:-60}"
mkdir -p "$HOME/.cache/value-finder/mos"
echo "$(date '+%Y-%m-%d %H:%M:%S') mos_pull_all: start ($ROOT)"

leg() {   # leg <project folder> <python> [mos_fetch.py args...]
    dir="$1"; py="$2"; shift 2
    sleep "$PAUSE_S"
    cd "$ROOT/$dir" || { echo "$(date '+%Y-%m-%d %H:%M:%S') mos_pull_all: $ROOT/$dir is gone; stopping"; exit 1; }
    caffeinate -i "$py" scripts/mos_fetch.py "$@"
}

leg cfb-weather "$PY_CFB" --seasons 2023-2025
leg cfb-weather "$PY_CFB"
leg nfl-weather "$PY_NFL"
echo "$(date '+%Y-%m-%d %H:%M:%S') mos_pull_all: finished"
