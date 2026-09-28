#!/usr/bin/env bash
# Copy the forward-test ledgers to the `ledgers` branch on GitHub, once a day.
# Uses its own clone (~/code/.value-finder-ledgers), so it never touches the
# working checkout or whatever branch a chat has open there. Each push is a
# dated, public-to-you record that the ledger existed in that state.
#   ops/sync_ledgers.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLONE="$HOME/code/.value-finder-ledgers"
REMOTE="$(git -C "$ROOT" remote get-url origin)"

if [ ! -d "$CLONE/.git" ]; then
  git clone --quiet --no-checkout "$REMOTE" "$CLONE"
  if git -C "$CLONE" ls-remote --exit-code --heads origin ledgers >/dev/null; then
    git -C "$CLONE" checkout --quiet ledgers
  else
    git -C "$CLONE" checkout --quiet --orphan ledgers
    git -C "$CLONE" rm -rf --quiet . 2>/dev/null || true
  fi
fi

cd "$CLONE"
git pull --quiet --ff-only origin ledgers 2>/dev/null || true
for p in nfl-weather cfb-weather; do
  mkdir -p "$p"
  cp "$ROOT/$p/data/forward/ledger.csv" "$p/ledger.csv"
  cp "$ROOT/$p/data/forward/alerts.log" "$p/alerts.log" 2>/dev/null || true
  cp "$ROOT/$p/data/forward/fills.csv" "$p/fills.csv" 2>/dev/null || true
done
git add -A
if git diff --cached --quiet; then
  echo "ledgers unchanged"
  exit 0
fi
git commit --quiet -m "Ledger snapshot $(date -u +%Y-%m-%dT%H:%MZ)"
git push --quiet -u origin ledgers
echo "ledgers pushed"
