#!/usr/bin/env bash
# SessionStart hook: build each project's virtual environment in cloud sessions.
# Does nothing on the Mac (CLAUDE_CODE_REMOTE is only "true" in a cloud VM),
# and skips any environment that already exists, so resumed sessions start fast.
set -euo pipefail
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

build_venv() {  # $1 = project folder with a requirements.txt
  if [ ! -x "$1/.venv/bin/python" ]; then
    uv venv --quiet --python 3.12 "$1/.venv"
    uv pip install --quiet --python "$1/.venv/bin/python" -r "$1/requirements.txt" pytest
  fi
}

build_venv nfl-weather &
build_venv cfb-weather &
(cd sharp-markets && uv sync --quiet) &
wait

# The forward-test ledgers live on the `ledgers` branch (see ops/sync_ledgers.sh).
git fetch --quiet origin ledgers 2>/dev/null || true
echo "value-finder: environments ready; ledgers at origin/ledgers"
