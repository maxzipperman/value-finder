#!/bin/zsh
# Full refresh: data -> every analysis -> report. Safe to rerun; downloads are cached.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
$PY scripts/fetch_data.py "$@"
$PY scripts/build_data.py
$PY scripts/replicate.py
$PY scripts/extend.py
$PY scripts/audit_thesis.py
$PY scripts/betting.py
$PY scripts/model_compare.py
$PY scripts/strategies.py
$PY scripts/this_week.py --no-fetch
$PY scripts/report_data.py
