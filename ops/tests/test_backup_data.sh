#!/bin/bash
# Tests for ops/backup_data.sh (the owner's page: ops/BACKUP.md).
#   ops/tests/test_backup_data.sh            exits 1 if any test fails
#   VERBOSE=1 ops/tests/test_backup_data.sh  also prints every run's output
# A fake checkout and home folder live in a temporary folder (under TMPDIR). A small disk image, made and attached
# with hdiutil, stands in for the other disk; it is detached and deleted at the end, with the temporary folder.
# Nothing outside that folder is written. "Another volume of the same physical disk" is tested with a stand-in for
# diskutil: a 64 MB image holds only one APFS volume, and mounting a second one where the test chooses needs root.
# Every run of the script is checked to leave the fake source exactly as it was (names, types, permissions, sizes,
# modification and change times, and the SHA-256 of every readable file) and to print no key.
set -u
export LC_ALL=C
HERE="$(cd "$(dirname "$0")" && pwd -P)"
SCRIPT="$(dirname "$HERE")/backup_data.sh"
T="$(mktemp -d "${TMPDIR:-/tmp}/vf-backup-tests.XXXXXX")"
IMGDEV=""
cleanup() {
  [ -z "$IMGDEV" ] || hdiutil detach "$IMGDEV" -force >/dev/null 2>&1 || echo "Could not detach the test disk $IMGDEV." >&2
  chmod -R u+rwx "$T" 2>/dev/null
  rm -rf "$T"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

PASSED=0 FAILED=0
pass() { PASSED=$((PASSED + 1)); printf 'ok    %s\n' "$1"; }
fail() { FAILED=$((FAILED + 1)); printf 'FAIL  %s\n' "$1"; }
expect() { local what="$1"; shift; if "$@"; then pass "$what"; else fail "$what"; fi; }
has() { printf '%s' "$OUT" | grep -qF -- "$1"; }
hasnt() { ! has "$1"; }
empty_dir() { [ -z "$(ls -A "$1")" ]; }
mk() { mkdir -p "$(dirname "$1")"; printf '%s' "$2" > "$1"; }

# ---- the fake source: a checkout, a home folder, and a folder outside both ------------------------------------------
S="$T/src"
R="$S/repo"
H="$S/home"
KEY="FAKE-KEY-5f1e0c93"                 # made up; it must never reach the backup or the output
NFLODDS="$R/sharp-markets/data/raw/americanfootball_nfl/oddsapi/hist_odds"
mk "$R/sharp-markets/data/raw/_manifest/oddsapi_manifest.csv" $'pull,requested,returned\nF1,a,b\n'
mk "$NFLODDS/2025-09-07/k1.json" '{"a":1}'
mk "$NFLODDS/2025-09-07/odds week 1.json" '{"with":"space"}'
mk "$R/sharp-markets/data/raw/nba/kalshi/2026-01-05/c.parquet" 'PAR1 candles'
mk "$R/sharp-markets/data/raw/americanfootball_nfl/.env" "ODDS_API_KEY=$KEY"     # a .env inside a copied folder
mk "$R/sharp-markets/data/raw/.DS_Store" 'finder'
mk "$R/sharp-markets/data/markets.duckdb" 'DUCK'
mk "$R/sharp-markets/.env" "ODDS_API_KEY=$KEY"
mk "$R/nfl-weather/.env" "ODDS_API_KEY=$KEY"
mk "$R/nfl-weather/.venv/bin/python" 'venv'
mk "$R/nfl-weather/data/raw/oddsapi/live/2026-09-29T183008Z.json" '{"live":1}'
mk "$R/nfl-weather/data/raw/oddsapi_hist/h.json" '{"hist":1}'
mk "$R/nfl-weather/data/raw/weather/w.csv" 'free weather: not copied'
mk "$R/nfl-weather/data/forward/ledger.csv" $'id,rule\n1,B\n'
mk "$R/nfl-weather/data/forward/runs.csv" $'run\n1\n'
mk "$R/nfl-weather/data/forward/forecasts/f1.json" '{}'
mk "$R/nfl-weather/data/forward/.env.local" "ODDS_API_KEY=$KEY"
chmod 000 "$R/nfl-weather/data/forward/.env.local"                      # unreadable: opening it would be an error
mk "$R/cfb-weather/data/raw/oddsapi/live/x.json" '{}'
mk "$R/cfb-weather/data/forward/ledger.csv" $'id\n1\n'
mk "$R/cfb-weather/data/forward/decisions.csv" $'decision_id\n'
mk "$R/cfb-weather/data/forward/.venv/x" 'a venv inside a copied folder'
mk "$R/cfb-weather/data/forward/.git/HEAD" 'a git folder inside a copied folder'
mk "$H/.cache/value-finder/mos/GFS/a.txt" 'forecast archive'
mk "$H/.cache/value-finder/odds_quota.json" '{}'
mk "$H/.cache/value-finder/.env" "ODDS_API_KEY=$KEY"
mk "$H/.kaggle/kaggle.json" "{\"key\":\"$KEY\"}"
mk "$S/outside/secret.txt" 'OUTSIDE-CONTENT-9c2b'
ln -s ../../../../../outside/secret.txt "$R/sharp-markets/data/raw/nba/link_to_outside.txt"
ln -s "$S/outside" "$R/sharp-markets/data/raw/nba/link_to_outside_folder"
[ "$(cat "$R/sharp-markets/data/raw/nba/link_to_outside.txt")" = OUTSIDE-CONTENT-9c2b ] || { echo "test setup: bad link" >&2; exit 1; }
find "$S" -exec touch -h -t 202609010000 {} +      # written well before any backup, as the real files are

# Names, types, permissions, sizes, times and hashes of everything in the fake source.
snapshot() {
  ( cd "$S" && find . -exec stat -f '%HT|%Sp|%z|%Fm|%Fc|%N' {} + | sort
    find . -type f -perm -0400 -exec shasum -a 256 {} + | sort )
}
# Names, sizes and times of everything under a destination.
dest_state() { ( cd "$1" && find . -exec stat -f '%HT|%z|%Fm|%N' {} + | sort ); }

# run NAME STATUS [VAR=value ...] -- ARGS...: run the script with HOME set to the fake home folder.
run() {
  local name="$1" want="$2" envs=()
  shift 2
  while [ $# -gt 0 ] && [ "$1" != "--" ]; do envs+=("$1"); shift; done
  shift
  snapshot > "$T/before"
  OUT="$(env -u MARKETS_DATA_DIR -u MARKETS_ROOT HOME="$H" ${envs[@]+"${envs[@]}"} "$SCRIPT" "$@" 2>&1)"
  STATUS=$?
  snapshot > "$T/after"
  expect "$name: exit status $want" [ "$STATUS" = "$want" ]
  expect "$name: the source is unchanged" cmp -s "$T/before" "$T/after"
  expect "$name: no key in the output" hasnt "$KEY"
  if [ "$STATUS" != "$want" ] || [ -n "${VERBOSE:-}" ]; then printf '%s\n' "$OUT" | sed 's/^/      | /'; fi
}

# ---- the other disk: a disk image -----------------------------------------------------------------------------------
MNT="$T/disk"
mkdir -p "$MNT"
if ! hdiutil create -quiet -size 64m -fs APFS -volname VFBackupTest "$T/disk.dmg"; then
  echo "hdiutil could not make a test disk image. These tests need macOS." >&2; exit 1
fi
IMGDEV="$(hdiutil attach -nobrowse -noverify -mountpoint "$MNT" "$T/disk.dmg" | awk 'NR == 1 { print $1 }')"
[ -n "$IMGDEV" ] || { echo "hdiutil could not attach the test disk image." >&2; exit 1; }
echo "Test disk: $IMGDEV at $MNT"

# ---- refusals ----------------------------------------------------------------------------------------------------------
run "a destination that does not exist" 2 -- "$MNT/nope" --repo "$R"
expect "  ... says so" has "does not exist"
expect "  ... creates nothing" [ ! -e "$MNT/nope" ]

mkdir -p "$T/same-disk"
run "a destination on the same disk as the source" 2 -- "$T/same-disk" --repo "$R"
expect "  ... says a copy on the same disk is not a backup" has "on the same disk as"
expect "  ... writes nothing there" empty_dir "$T/same-disk"

mkdir -p "$R/backups"
run "a destination inside the checkout" 2 -- "$R/backups" --repo "$R"
expect "  ... says so" has "inside the checkout"
expect "  ... writes nothing there" empty_dir "$R/backups"

ICLOUD="$MNT/Users/max/Library/Mobile Documents/com~apple~CloudDocs/VF backup"
mkdir -p "$ICLOUD"
run "a destination that looks like iCloud Drive" 2 -- "$ICLOUD" --repo "$R"
expect "  ... names iCloud Drive and --allow-cloud" has "iCloud Drive copies to the internet"
expect "  ... writes nothing there" empty_dir "$ICLOUD"
run "the same with --allow-cloud" 0 -- "$ICLOUD" --repo "$R" --allow-cloud
expect "  ... copies and checks" has "OK    Group 1, the paid data"

mkdir -p "$MNT/locked"
chmod 555 "$MNT/locked"
run "a destination that can't be written to" 2 -- "$MNT/locked" --repo "$R"
expect "  ... says so" has "can't be written to"

BIG="$S/bigrepo"
mkdir -p "$BIG/nfl-weather/data/forward" "$BIG/cfb-weather/data/forward" "$BIG/sharp-markets/data/raw"
dd if=/dev/zero of="$BIG/sharp-markets/data/raw/big.bin" bs=1048576 count=0 seek=200 2>/dev/null   # 200 MB, sparse
mkdir -p "$MNT/space"
run "too little space on the destination (a 64 MB disk, 200 MB to copy)" 2 -- "$MNT/space" --repo "$BIG"
expect "  ... says how much it needs" has "free, and this backup needs about"
expect "  ... writes nothing there" empty_dir "$MNT/space"
rm -rf "$BIG"

# A stand-in diskutil that puts every volume on one physical disk, as two volumes of this Mac's own disk would be.
mkdir -p "$T/stub"
printf '#!/bin/sh\necho "   Part of Whole:             disk99"\n' > "$T/stub/diskutil"
chmod +x "$T/stub/diskutil"
mkdir -p "$MNT/volume2"
run "a destination on another volume of the same physical disk (stand-in diskutil)" 2 PATH="$T/stub:$PATH" -- "$MNT/volume2" --repo "$R"
expect "  ... says so" has "is another volume of the same physical disk (disk99)"
expect "  ... writes nothing there" empty_dir "$MNT/volume2"
expect "the real diskutil tells the test disk from this Mac's disk" \
  [ "$(diskutil info "$MNT" | awk -F': *' '/^ *Part of Whole:/ { print $2; exit }')" != \
    "$(diskutil info "$(df -P "$S" | awk 'NR == 2 { print $1 }')" | awk -F': *' '/^ *Part of Whole:/ { print $2; exit }')" ]

# ---- a first backup ----------------------------------------------------------------------------------------------------
D="$MNT/drive"
BK="$D/value-finder-backup"
mkdir -p "$D"
run "first backup" 0 -- "$D" --repo "$R"
expect "  ... group 1 OK" has "OK    Group 1, the paid data: 7 files and 2 links"
expect "  ... group 2 OK, snapshot included" has "OK    Group 2, the forward-test records: 5 files"
expect "  ... group 2 checked in the snapshot too" has "on the backup and in the snapshot forward-snapshots/"
expect "  ... group 3 copied" has "--    Group 3, slow to re-create: 3 files"
expect "  ... the manifest is copied" cmp -s "$R/sharp-markets/data/raw/_manifest/oddsapi_manifest.csv" "$BK/sharp-markets/data/raw/_manifest/oddsapi_manifest.csv"
expect "  ... a file name with a space is copied" cmp -s "$NFLODDS/2025-09-07/odds week 1.json" "$BK/sharp-markets/data/raw/americanfootball_nfl/oddsapi/hist_odds/2025-09-07/odds week 1.json"
expect "  ... every oddsapi* folder is copied" cmp -s "$R/nfl-weather/data/raw/oddsapi_hist/h.json" "$BK/nfl-weather/data/raw/oddsapi_hist/h.json"
expect "  ... cfb-weather's oddsapi folder is copied" [ -f "$BK/cfb-weather/data/raw/oddsapi/live/x.json" ]
expect "  ... the ledger is copied" cmp -s "$R/nfl-weather/data/forward/ledger.csv" "$BK/nfl-weather/data/forward/ledger.csv"
expect "  ... the decision record is copied" cmp -s "$R/cfb-weather/data/forward/decisions.csv" "$BK/cfb-weather/data/forward/decisions.csv"
expect "  ... the forecast archive is copied" [ -f "$BK/home-cache/value-finder/mos/GFS/a.txt" ]
expect "  ... markets.duckdb is copied" cmp -s "$R/sharp-markets/data/markets.duckdb" "$BK/sharp-markets/data/markets.duckdb"
expect "  ... times are kept" [ "$(stat -f %m "$R/nfl-weather/data/forward/ledger.csv")" = "$(stat -f %m "$BK/nfl-weather/data/forward/ledger.csv")" ]
expect "  ... no .env file anywhere on the backup" [ -z "$(find "$D" -name '.env*')" ]
expect "  ... the key is nowhere on the backup" sh -c '! grep -rqF "$1" "$2"' - "$KEY" "$D"
expect "  ... no .venv, .git, .kaggle or .DS_Store" [ -z "$(find "$D" \( -name .venv -o -name .git -o -name .kaggle -o -name .DS_Store \))" ]
expect "  ... a link is copied as a link" [ -L "$BK/sharp-markets/data/raw/nba/link_to_outside.txt" ]
expect "  ... pointing where it pointed" [ "$(readlink "$BK/sharp-markets/data/raw/nba/link_to_outside.txt")" = ../../../../../outside/secret.txt ]
expect "  ... a link to a folder is copied as a link" [ -L "$BK/sharp-markets/data/raw/nba/link_to_outside_folder" ]
expect "  ... what the links point to is not copied" sh -c '! grep -rqF OUTSIDE-CONTENT "$1"' - "$D"
expect "  ... folders not on the list are not copied" [ ! -e "$BK/nfl-weather/data/raw/weather" ]
expect "  ... one snapshot" [ "$(ls "$BK/forward-snapshots" | wc -l | tr -d ' ')" = 1 ]
SNAP1="$BK/forward-snapshots/$(ls "$BK/forward-snapshots")"
expect "  ... the snapshot holds the ledger" cmp -s "$R/nfl-weather/data/forward/ledger.csv" "$SNAP1/nfl-weather/data/forward/ledger.csv"
expect "  ... the log has one line" [ "$(wc -l < "$BK/backup-log.txt" | tr -d ' ')" = 1 ]

# ---- a second backup, after a file changed, files were added and one was removed ------------------------------------------
OLD_LEDGER="$(cat "$R/nfl-weather/data/forward/ledger.csv")"
printf '2,B\n' >> "$R/nfl-weather/data/forward/ledger.csv"
printf 'F2,c,d\n' >> "$R/sharp-markets/data/raw/_manifest/oddsapi_manifest.csv"
mk "$NFLODDS/2025-09-14/k2.json" '{"b":2}'
mk "$R/cfb-weather/data/forward/forecasts/new.json" '{"new":1}'
rm "$R/sharp-markets/data/raw/nba/kalshi/2026-01-05/c.parquet"
run "second backup" 0 -- "$D" --repo "$R"
expect "  ... group 1 OK" has "OK    Group 1, the paid data: 7 files and 2 links"
expect "  ... group 2 OK" has "OK    Group 2, the forward-test records: 6 files"
expect "  ... the changed ledger is copied again under its name" cmp -s "$R/nfl-weather/data/forward/ledger.csv" "$BK/nfl-weather/data/forward/ledger.csv"
expect "  ... the grown manifest is copied again" cmp -s "$R/sharp-markets/data/raw/_manifest/oddsapi_manifest.csv" "$BK/sharp-markets/data/raw/_manifest/oddsapi_manifest.csv"
expect "  ... an added paid file is copied" [ -f "$BK/sharp-markets/data/raw/americanfootball_nfl/oddsapi/hist_odds/2025-09-14/k2.json" ]
expect "  ... an added forward file is copied" [ -f "$BK/cfb-weather/data/forward/forecasts/new.json" ]
expect "  ... a file removed from this Mac stays on the backup" [ -f "$BK/sharp-markets/data/raw/nba/kalshi/2026-01-05/c.parquet" ]
expect "  ... two snapshots" [ "$(ls "$BK/forward-snapshots" | wc -l | tr -d ' ')" = 2 ]
expect "  ... the first snapshot still holds the ledger as it was" [ "$(cat "$SNAP1/nfl-weather/data/forward/ledger.csv")" = "$OLD_LEDGER" ]
SNAP2="$BK/forward-snapshots/$(ls "$BK/forward-snapshots" | tail -1)"
expect "  ... the second snapshot holds the new ledger" cmp -s "$R/nfl-weather/data/forward/ledger.csv" "$SNAP2/nfl-weather/data/forward/ledger.csv"
expect "  ... the log has two lines" [ "$(wc -l < "$BK/backup-log.txt" | tr -d ' ')" = 2 ]

# ---- --check ---------------------------------------------------------------------------------------------------------------
dest_state "$D" > "$T/dest-before"
run "--check on a good backup" 0 -- "$D" --repo "$R" --check
expect "  ... group 1 OK" has "OK    Group 1, the paid data"
expect "  ... group 2 OK" has "OK    Group 2, the forward-test records"
expect "  ... says it finished" has "Check finished: groups 1 and 2 match"
dest_state "$D" > "$T/dest-after"
expect "  ... writes nothing on the backup" cmp -s "$T/dest-before" "$T/dest-after"

printf '3,B\n' >> "$R/nfl-weather/data/forward/ledger.csv"             # an alert run, after the last backup
run "--check after a job wrote a record since the last backup" 0 -- "$D" --repo "$R" --check
expect "  ... group 2 OK, listing the newer file" has "new or changed on this Mac since the last backup"
expect "  ... names it" has "nfl-weather/data/forward/ledger.csv: new or changed since the last backup"
expect "  ... no FAIL" hasnt "FAIL"
expect "  ... and its last line says what was left out" has "apart from what was written on this Mac since the last backup"

COPY="$BK/sharp-markets/data/raw/americanfootball_nfl/oddsapi/hist_odds/2025-09-07/odds week 1.json"
printf 'X' | dd of="$COPY" bs=1 seek=3 conv=notrunc 2>/dev/null        # one byte changed on the backup,
touch -r "$NFLODDS/2025-09-07/odds week 1.json" "$COPY"                    # with its size and time as before
dest_state "$D" > "$T/dest-before"
run "--check after one byte of a copied file was changed on the backup" 1 -- "$D" --repo "$R" --check
expect "  ... group 1 FAIL" has "FAIL  Group 1, the paid data"
expect "  ... names the file" has "sharp-markets/data/raw/americanfootball_nfl/oddsapi/hist_odds/2025-09-07/odds week 1.json: differs (content)"
expect "  ... group 2 still OK" has "OK    Group 2, the forward-test records"
expect "  ... says there are problems" has "Check found problems"
dest_state "$D" > "$T/dest-after"
expect "  ... writes nothing on the backup" cmp -s "$T/dest-before" "$T/dest-after"

rm "$BK/nfl-weather/data/forward/runs.csv"
run "--check after a copied file was deleted on the backup" 1 -- "$D" --repo "$R" --check
expect "  ... names it as missing" has "nfl-weather/data/forward/runs.csv: missing on the backup"
expect "  ... group 2 FAIL" has "FAIL  Group 2, the forward-test records"

run "a backup after that: copies the missing file, keeps and reports the damaged one" 1 -- "$D" --repo "$R"
expect "  ... the missing file is back" cmp -s "$R/nfl-weather/data/forward/runs.csv" "$BK/nfl-weather/data/forward/runs.csv"
expect "  ... group 2 OK again" has "OK    Group 2, the forward-test records"
expect "  ... the damaged copy is still reported, not overwritten silently" has "odds week 1.json: differs (content)"

mv "$R/cfb-weather/data/raw/oddsapi" "$S/oddsapi.moved"
run "--check when a paid-data folder is gone from this Mac" 1 -- "$D" --repo "$R" --check
expect "  ... says it is not on this Mac" has "cfb-weather/data/raw/oddsapi: not on this Mac"
mv "$S/oddsapi.moved" "$R/cfb-weather/data/raw/oddsapi"

# A job writes to a record while a backup runs: a stand-in rsync appends to the cfb-weather ledger right after it copies
# that folder. This run changes the source on purpose, so it is not wrapped in run().
mkdir -p "$T/stub-rsync"
cat > "$T/stub-rsync/rsync" <<'STUB'
#!/bin/sh
/usr/bin/rsync "$@"; rc=$?
case "$*" in
  *cfb-weather/data/forward/*) [ -e "$FLAG" ] || { touch "$FLAG"; printf 'written during the backup\n' >> "$TARGET"; } ;;
esac
exit $rc
STUB
chmod +x "$T/stub-rsync/rsync"
D4="$MNT/drive4"
mkdir -p "$D4"
OUT="$(env -u MARKETS_DATA_DIR -u MARKETS_ROOT HOME="$H" PATH="$T/stub-rsync:$PATH" FLAG="$T/stub-rsync/done" \
       TARGET="$R/cfb-weather/data/forward/ledger.csv" "$SCRIPT" "$D4" --repo "$R" 2>&1)"
STATUS=$?
expect "a record written while a backup runs: exit status 1" [ "$STATUS" = 1 ]
expect "  ... names it and says it changed while the backup ran" has "cfb-weather/data/forward/ledger.csv: differs (size), changed on this Mac while this ran"
expect "  ... the stand-in did write during the run" [ -e "$T/stub-rsync/done" ]
expect "  ... no key in the output" hasnt "$KEY"
[ -z "${VERBOSE:-}" ] || printf '%s\n' "$OUT" | sed 's/^/      | /'
run "the same backup run again" 0 -- "$D4" --repo "$R"
expect "  ... group 2 OK" has "OK    Group 2, the forward-test records"

# ---- MARKETS_DATA_DIR ------------------------------------------------------------------------------------------------------
ALT="$S/alt-data"
mk "$ALT/raw/_manifest/oddsapi_manifest.csv" 'the manifest in the moved data folder'
mk "$ALT/markets.duckdb" 'ALTDUCK'
D3="$MNT/drive3"
mkdir -p "$D3"
run "a backup with MARKETS_DATA_DIR set" 0 MARKETS_DATA_DIR="$ALT" -- "$D3" --repo "$R"
expect "  ... says where the data folder is" has "The sharp-markets data folder is $ALT"
expect "  ... copies that folder's raw data" cmp -s "$ALT/raw/_manifest/oddsapi_manifest.csv" "$D3/value-finder-backup/sharp-markets/data/raw/_manifest/oddsapi_manifest.csv"
expect "  ... and that folder's markets.duckdb" cmp -s "$ALT/markets.duckdb" "$D3/value-finder-backup/sharp-markets/data/markets.duckdb"
expect "  ... not the default folder's" [ ! -e "$D3/value-finder-backup/sharp-markets/data/raw/americanfootball_nfl" ]

echo
echo "$PASSED passed, $FAILED failed."
[ "$FAILED" -eq 0 ]
