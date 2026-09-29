#!/bin/sh
# The whole GFS MOS pull for issue #40: CFB 2023-25 first (the validation sample), then CFB
# 2006-25, then NFL 2004-25. Cache-first: a rerun skips every window already downloaded, so this
# is also the command that finishes an interrupted pull. Free (Iowa Environmental Mesonet), no key.
# Keeps the Mac awake while it runs (caffeinate -i ends with it) and logs to the shared cache.
#
#   nohup cfb-weather/scripts/mos_pull_all.sh > ~/.cache/value-finder/mos/fetch_full.log 2>&1 &
#
# Each project's Python defaults to its own .venv; set PY_CFB / PY_NFL to use another.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY_CFB="${PY_CFB:-$ROOT/cfb-weather/.venv/bin/python}"
PY_NFL="${PY_NFL:-$ROOT/nfl-weather/.venv/bin/python}"
mkdir -p "$HOME/.cache/value-finder/mos"
echo "$(date '+%Y-%m-%d %H:%M:%S') mos_pull_all: start ($ROOT)"
cd "$ROOT/cfb-weather" && caffeinate -i "$PY_CFB" scripts/mos_fetch.py --seasons 2023-2025
cd "$ROOT/cfb-weather" && caffeinate -i "$PY_CFB" scripts/mos_fetch.py
cd "$ROOT/nfl-weather" && caffeinate -i "$PY_NFL" scripts/mos_fetch.py
echo "$(date '+%Y-%m-%d %H:%M:%S') mos_pull_all: finished"
