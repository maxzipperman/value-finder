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

# The published decision record never loses a line (nfl-weather amendment 7, cfb-weather amendment 5,
# section 3). A project's decisions.csv replaces its published copy only when it still holds every line of
# that copy, byte for byte. A file that is missing, empty, cut (its last line has no line break), does not
# start with the record's header line, or has lost or changed a published line is not published: the
# published copy is kept as it is, one line says so, and every other file is synced as usual. The same
# checks guard the first copy. A published copy that is itself damaged (cut, or not starting with the
# header) is never replaced here: the line says so, and the hub replaces it by hand. The sync never fails
# over any of this. The header is the scorers' RECORD_COLS (a test checks that they agree).
RECORD_HEADER="decision_id,rule,horizon,horizon_utc,decided_utc,n_bets,verdict,numbers,ledger_rows,ledger_rows_sha256"

# Why a record file can't be published (nothing when it can): missing, empty, cut, or a first line that is not
# the record's header. A header line ending in a carriage return is accepted, as the scorers read it.
record_damage() {
  local f="$1" first=""
  if [ ! -f "$f" ]; then
    echo "the file is missing"
  elif [ ! -s "$f" ]; then
    echo "the file is empty"
  elif [ -n "$(tail -c 1 "$f")" ]; then
    echo "its last line is cut, with no line break at the end"
  else
    first="$(head -n 1 "$f")"
    if [ "${first%$'\r'}" != "$RECORD_HEADER" ]; then
      echo "its first line is not the record's header"
    fi
  fi
  return 0
}

publish_decisions() {
  local p="$1" new="$ROOT/$1/data/forward/decisions.csv" old="$1/decisions.csv" why="" rc=0
  if [ ! -e "$old" ] && [ ! -e "$new" ]; then
    return 0                                # no decision recorded and nothing published yet: nothing to do
  fi
  if [ -s "$old" ]; then
    why="$(record_damage "$old")"
    if [ -n "$why" ]; then
      echo "$p: decisions.csv not published (the published copy is damaged: $why); the published copy is kept" \
           "as it is, and the hub replaces it by hand"
      return 0
    fi
  fi
  why="$(record_damage "$new")"
  if [ -z "$why" ] && [ -s "$old" ]; then
    # awk exits 0 when a line of the published copy is not a line of the new file, 1 when every line is
    awk -v new="$new" 'FILENAME == new { have[$0] = 1; next } !($0 in have) { lost = 1 }
                       END { exit (lost ? 0 : 1) }' "$new" "$old" || rc=$?
    if [ "$rc" -eq 0 ]; then
      why="it has lost or changed a line that the published copy holds"
    elif [ "$rc" -ne 1 ]; then
      why="it could not be compared with the published copy"
    fi
  fi
  if [ -n "$why" ]; then
    if [ -e "$old" ]; then
      echo "$p: decisions.csv not published ($why); the published copy is kept as it is"
    else
      echo "$p: decisions.csv not published ($why); nothing has been published for it yet"
    fi
    return 0
  fi
  cp "$new" "$old"
}

cd "$CLONE"
git pull --quiet --ff-only origin ledgers 2>/dev/null || true
for p in nfl-weather cfb-weather; do
  mkdir -p "$p"
  cp "$ROOT/$p/data/forward/ledger.csv" "$p/ledger.csv"
  cp "$ROOT/$p/data/forward/alerts.log" "$p/alerts.log" 2>/dev/null || true
  cp "$ROOT/$p/data/forward/closes.csv" "$p/closes.csv" 2>/dev/null || true
  publish_decisions "$p"
  cp "$ROOT/$p/data/forward/runs.csv" "$p/runs.csv" 2>/dev/null || true
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
