#!/bin/zsh
# Rerun the menu-bar light's self-tests and compare each with menubar/tests/expected/.
# It starts a stand-in for the dashboard (stub_server.py) on a free port of 127.0.0.1,
# runs the built app with --selftest once per case, and then checks that the app asked
# each address exactly once, followed no redirect, refused addresses off this Mac, only
# ever connected to the stand-in, and left no cache or saved-state files behind.
# It reads the app and writes only to a temporary folder (and to expected/ with --update).
#   menubar/tests/run_selftests.sh            compare; exits 1 on any difference
#   menubar/tests/run_selftests.sh --update   rewrite the expected files
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MENUBAR="$(dirname "$HERE")"
BIN="$MENUBAR/build/Value Finder.app/Contents/MacOS/ValueFinder"
EXPECTED="$HERE/expected"
PY=/usr/bin/python3
UPDATE=0
[[ "${1:-}" == "--update" ]] && UPDATE=1
[[ -x "$BIN" ]] || { echo "No app to test. Build it first: ops/build_menubar.sh" >&2; exit 1; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/vf-menubar-tests.XXXXXX")"
SERVER_PID=""
cleanup() {
  [[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT INT TERM
touch "$WORK/started"

"$PY" "$HERE/stub_server.py" > "$WORK/port" 2> "$WORK/requests.log" &
SERVER_PID=$!
for _ in {1..100}; do [[ -s "$WORK/port" ]] && break; sleep 0.1; done
PORT="$(head -1 "$WORK/port")"
[[ "$PORT" == <-> ]] || { echo "The stand-in server did not start." >&2; exit 1; }
# A port with nothing listening, for the "no server at all" case.
DEAD_PORT="$("$PY" -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"

normalize() { sed -E 's/Checked at [0-9]{1,2}:[0-9]{2} (AM|PM)/Checked at <time>/'; }

CASES=(ok-no-signals ok-two-signals warn-one-problem fail-two-problems invalid-json
       missing-field wrong-type no-server credits-null boolean-count unknown-health
       http-error redirect many-problems extra-field utc-offset hang)
FAILED=0
ASKED=()
for name in $CASES; do
  if [[ "$name" == no-server ]]; then
    url="http://127.0.0.1:$DEAD_PORT/api/summary"
  else
    url="http://127.0.0.1:$PORT/$name"
    ASKED+=("GET /$name")
  fi
  "$BIN" --selftest "$url" | normalize > "$WORK/$name.txt"
  if (( UPDATE )); then
    cp "$WORK/$name.txt" "$EXPECTED/$name.txt"
    echo "updated  $name"
  elif diff -u "$EXPECTED/$name.txt" "$WORK/$name.txt" > "$WORK/$name.diff"; then
    echo "ok       $name"
  else
    echo "DIFFERS  $name"; cat "$WORK/$name.diff"; FAILED=1
  fi
done

check() {  # check <description> <command...>
  local what="$1"; shift
  if "$@"; then echo "ok       $what"; else echo "FAILED   $what"; FAILED=1; fi
}

# Each case's address was asked exactly once, in order, and the redirect was not followed.
print -rl -- $ASKED > "$WORK/asked.expected"
check "each address asked exactly once, no redirect followed" \
  diff -u "$WORK/asked.expected" "$WORK/requests.log"

# Addresses off this Mac are refused before anything is sent.
refused() { "$BIN" --selftest "$1" > /dev/null 2>&1; [[ $? -eq 64 ]]; }
check "refuses https://example.com/api/summary" refused "https://example.com/api/summary"
check "refuses http://localhost:$PORT/ok-no-signals" refused "http://localhost:$PORT/ok-no-signals"
check "refuses http://127.0.0.1@example.com/" refused "http://127.0.0.1@example.com/"
check "refuses http://127.0.0.1.example.com/" refused "http://127.0.0.1.example.com/"
check "refuses a missing address" refused ""

# Watch the app's network connections while it waits on a slow answer.
"$BIN" --selftest "http://127.0.0.1:$PORT/slow" > /dev/null &
APP_PID=$!
sleep 1
lsof -a -p "$APP_PID" -i -n -P -F n > "$WORK/lsof.txt" 2>/dev/null || true
wait "$APP_PID" || true
grep '^n' "$WORK/lsof.txt" | sed 's/^n//' > "$WORK/connections.txt" || true
only_local_connection() {
  [[ -s "$WORK/connections.txt" ]] || { echo "   (no connection seen)"; return 1; }
  sed 's/^/   seen: /' "$WORK/connections.txt"
  ! grep -qv -- "^127\.0\.0\.1:[0-9]*->127\.0\.0\.1:$PORT\$" "$WORK/connections.txt"
}
check "its only connection was to 127.0.0.1:$PORT" only_local_connection

# No cache, cookie store or saved window state was written for the app.
no_files_written() {
  local found
  found="$(find "$HOME/Library/Caches" "$HOME/Library/HTTPStorages" "$HOME/Library/Containers" \
                "$HOME/Library/Saved Application State" -maxdepth 1 -name 'com.valuefinder.menubar*' \
                -newer "$WORK/started" 2>/dev/null)"
  [[ -z "$found" ]] || { echo "$found" | sed 's/^/   written: /'; return 1; }
}
check "no cache, cookie or saved-state files written" no_files_written

# Read the code: the only addresses in it are the two fixed ones, the browser is only ever
# sent to the dashboard, and nothing starts a program, touches a file or sends a notification.
SOURCES=("$MENUBAR"/Sources/*.swift)
only_two_addresses() {
  local found
  # (The usage message's example, http://127.0.0.1:<port>/<path>, is not an address.)
  found="$(grep -ohE 'https?://[^"]*' $SOURCES | grep -v '<port>' | sort -u | tr '\n' ' ')"
  echo "   addresses in the code: $found"
  [[ "$found" == "http://127.0.0.1:8787/ http://127.0.0.1:8787/api/summary " ]]
}
check "the code names only the dashboard and its summary" only_two_addresses
browser_opens_only_dashboard() {
  local opens
  opens="$(grep -hoE 'NSWorkspace[^)]*\)' $SOURCES | sort -u)"
  echo "   browser: $opens"
  [[ "$opens" == "NSWorkspace.shared.open(Address.dashboard)" ]]
}
check "the browser is only ever sent to the dashboard" browser_opens_only_dashboard
FORBIDDEN='Process\(|NSTask|posix_spawn|popen|system\(|execv|NSAppleScript|UserNotifications|UNUserNotification|NSUserNotification|FileManager|FileHandle\(for|\.write\(to|contentsOf|fopen|\.env\b|launchctl'
nothing_forbidden() {
  ! grep -nE "$FORBIDDEN" $SOURCES | sed 's/^/   found: /' | grep .
}
check "no programs started, files touched or notifications sent" nothing_forbidden

(( UPDATE )) && echo "Expected files rewritten; review them with git diff."
(( FAILED )) && { echo "Some self-tests failed."; exit 1; }
echo "All self-tests passed."
