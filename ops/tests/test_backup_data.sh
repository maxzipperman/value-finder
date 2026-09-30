#!/bin/bash
# Tests for ops/backup_data.sh (the owner's page: ops/BACKUP.md).
#   ops/tests/test_backup_data.sh            exits 1 if any test fails
#   VERBOSE=1 ops/tests/test_backup_data.sh  also prints every run's output
# A fake checkout and home folder live in a temporary folder (under TMPDIR). A small disk image, made and attached
# with hdiutil, holds the destinations; it is detached and deleted at the end, with the temporary folder. Nothing
# outside that folder is written.
# The image's file sits in TMPDIR, on this Mac's own disk, so the script rightly refuses it as "the same disk" (tested
# with the real diskutil and hdiutil). Every other run uses a stand-in diskutil that reports the image as a USB drive.
# "Another volume of the same physical disk" and "another Mac" are tested with stand-ins for diskutil and ioreg.
# Every run of the script is checked to leave the fake source exactly as it was (names, types, permissions, sizes,
# modification and change times, and the SHA-256 of every readable file) and to print no key.
set -u
export LC_ALL=C
HERE="$(cd "$(dirname "$0")" && pwd -P)"
SCRIPT="$(dirname "$HERE")/backup_data.sh"
T="$(mktemp -d "${TMPDIR:-/tmp}/vf-backup-tests.XXXXXX")" && T="$(cd "$T" && pwd -P)" || exit 1
IMGDEV="" NESTDEV="" EXDEV=""
cleanup() {
  [ -z "$NESTDEV" ] || hdiutil detach "$NESTDEV" -force >/dev/null 2>&1 || echo "Could not detach the test disk $NESTDEV." >&2
  [ -z "$EXDEV" ] || hdiutil detach "$EXDEV" -force >/dev/null 2>&1 || echo "Could not detach the test disk $EXDEV." >&2
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
has2() { has "$1" && has "$2"; }
plain() { [ -f "$1" ] && [ ! -L "$1" ]; }                  # a regular file, not a link
plain_same() { plain "$1" && cmp -s "$1" "$2"; }            # ... with the same contents as $2
same2() { cmp -s "$1" "$2" && cmp -s "$3" "$4"; }
link_and_folder() { [ -L "$1" ] && [ -d "$2" ]; }
empty_dir() { [ -z "$(ls -A "$1")" ]; }
mk() { mkdir -p "$(dirname "$1")"; printf '%s' "$2" > "$1"; }
nsnaps() { ls "$1/forward-snapshots" | wc -l | tr -d ' '; }             # finished snapshots (ls hides .incomplete-*)
nincomplete() { ls -a "$1/forward-snapshots" | grep -c '^\.incomplete-'; }
snaps_are() { [ "$(nsnaps "$1")" = "$2" ] && [ "$(nincomplete "$1")" = "$3" ]; }   # finished, and .incomplete-

# ---- the fake source: a checkout, a home folder, and a folder outside both ------------------------------------------
S="$T/src"
R="$S/repo"
H="$S/home"
KEY="FAKE-KEY-5f1e0c93"                 # made up; it must never reach the backup or the output
RAW="$R/sharp-markets/data/raw"
NFLODDS="$RAW/americanfootball_nfl/oddsapi/hist_odds"
MANIFEST="$RAW/_manifest/oddsapi_manifest.csv"
mk "$MANIFEST" $'pull,requested,returned\nF1,a,b\n'
mk "$NFLODDS/2025-09-07/k1.json" '{"a":1}'
mk "$NFLODDS/2025-09-07/odds week 1.json" '{"with":"space"}'
mk "$RAW/nba/kalshi/2026-01-05/c.parquet" 'PAR1 candles'
mk "$RAW/americanfootball_nfl/.env" "ODDS_API_KEY=$KEY"     # key files inside a copied folder
for n in .env~ .envrc prod.env secrets.env env kaggle.json .env.local; do mk "$RAW/nba/$n" "ODDS_API_KEY=$KEY"; done
mk "$RAW/nba/deep/er/and/deeper/.env" "ODDS_API_KEY=$KEY"
# Key files named in capitals or mixed case (this Mac's disk ignores case: .ENV is the file programs open as .env), and
# other names that look like keys. Each in a folder of its own, as .ENV and .Env would be one file in one folder.
CASED=(.ENV .Env Prod.ENV KAGGLE.JSON ID_ED25519 SERVER.PEM Secret.txt Credentials.json API_SECRET .NETRC ENV
       api_key.txt odds_api.key token.json .odds_api_key service-account.json db_password.txt)
CASEDAT=()
for n in "${CASED[@]}"; do CASEDAT+=("cased/${#CASEDAT[@]}/$n"); mk "$RAW/nba/cased/$((${#CASEDAT[@]} - 1))/$n" "ODDS_API_KEY=$KEY"; done
mk "$RAW/.DS_Store" 'finder'
mk "$RAW/nba/kalshi/x.parquet.tmp" 'half written'
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
mk "$R/nfl-weather/data/forward/alert_state.json" '{"g1":{"sent":["a","b","c"]}}'
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
mk "$H/.cache/value-finder/Secrets.json" "ODDS_API_KEY=$KEY"
mk "$H/.kaggle/kaggle.json" "{\"key\":\"$KEY\"}"
mk "$S/outside/secret.txt" 'OUTSIDE-CONTENT-9c2b'
ln -s ../../../../../outside/secret.txt "$RAW/nba/link_to_outside.txt"
ln -s "$S/outside" "$RAW/nba/link_to_outside_folder"
[ "$(cat "$RAW/nba/link_to_outside.txt")" = OUTSIDE-CONTENT-9c2b ] || { echo "test setup: bad link" >&2; exit 1; }
find "$S" -exec touch -h -t 202609010000 {} +      # written well before any backup, as the real files are

# Names, types, permissions, sizes, times and hashes of everything in the fake source.
snapshot() {
  ( cd "$S" && find . -exec stat -f '%HT|%Sp|%z|%Fm|%Fc|%N' {} + | sort
    find . -type f -perm -0400 -exec shasum -a 256 {} + | sort )
}
# Names, sizes and times of everything under a destination.
dest_state() { ( cd "$1" && find . -exec stat -f '%HT|%z|%Fm|%N' {} + | sort ); }

# ---- the disk image, and the stand-ins -------------------------------------------------------------------------------
MNT="$T/disk"
mkdir -p "$MNT"
if ! hdiutil create -quiet -size 64m -fs APFS -volname VFBackupTest "$T/disk.dmg"; then
  echo "hdiutil could not make a test disk image. These tests need macOS." >&2; exit 1
fi
ATTACH="$(hdiutil attach -nobrowse -noverify -mountpoint "$MNT" "$T/disk.dmg")"
IMGDEV="$(printf '%s\n' "$ATTACH" | awk 'NR == 1 { print $1 }')"
[ -n "$IMGDEV" ] || { echo "hdiutil could not attach the test disk image." >&2; exit 1; }
USB_NODES="$(printf '%s\n' "$ATTACH" | awk '$1 ~ /^\/dev\/disk/ { sub(/^\/dev\//, "", $1); printf "%s ", $1 }')"
echo "Test disk: $IMGDEV at $MNT (its nodes: $USB_NODES)"
# A diskutil that reports the test disk image as a USB drive, and passes everything else through.
mkdir -p "$T/usb"
cat > "$T/usb/diskutil" <<'STUB'
#!/bin/sh
out="$(/usr/sbin/diskutil "$@")"; rc=$?
n="${2#/dev/}"
case " $USB_NODES " in *" $n "*) printf '%s\n' "$out" | sed 's/Disk Image/USB/' ;; *) printf '%s\n' "$out" ;; esac
exit $rc
STUB
chmod +x "$T/usb/diskutil"
# An ioreg that reports another Mac.
mkdir -p "$T/othermac"
printf '#!/bin/sh\necho %s\n' "'    \"IOPlatformUUID\" = \"00000000-0000-0000-0000-0000000BEEF0\"'" > "$T/othermac/ioreg"
chmod +x "$T/othermac/ioreg"

# run NAME STATUS [VAR=value ...] -- ARGS...: run the script with HOME set to the fake home folder and the USB stand-in
# first on PATH (a VAR=value given here comes later, so PATH=... replaces it).
run() {
  local name="$1" want="$2" envs=()
  shift 2
  while [ $# -gt 0 ] && [ "$1" != "--" ]; do envs+=("$1"); shift; done
  shift
  snapshot > "$T/before"
  OUT="$(env -u MARKETS_DATA_DIR -u MARKETS_ROOT HOME="$H" USB_NODES="$USB_NODES" PATH="$T/usb:$PATH" \
         ${envs[@]+"${envs[@]}"} "$SCRIPT" "$@" 2>&1)"
  STATUS=$?
  snapshot > "$T/after"
  expect "$name: exit status $want" [ "$STATUS" = "$want" ]
  expect "$name: the source is unchanged" cmp -s "$T/before" "$T/after"
  expect "$name: no key in the output" hasnt "$KEY"
  if [ "$STATUS" != "$want" ] || [ -n "${VERBOSE:-}" ]; then printf '%s\n' "$OUT" | sed 's/^/      | /'; fi
}

# ---- refusals ----------------------------------------------------------------------------------------------------------
run "a destination that does not exist" 2 -- "$MNT/nope" --repo "$R"
expect "  ... says so" has "does not exist"
expect "  ... creates nothing" [ ! -e "$MNT/nope" ]

mkdir -p "$T/same-disk"
run "a destination on the same disk as the source" 2 -- "$T/same-disk" --repo "$R"
expect "  ... says a copy on the same disk is not a backup" has "on the same disk as"
expect "  ... writes nothing there" empty_dir "$T/same-disk"

mkdir -p "$MNT/image-on-this-disk"
run "a disk image whose file is on this Mac's disk (real diskutil and hdiutil)" 2 PATH="$PATH" -- "$MNT/image-on-this-disk" --repo "$R"
expect "  ... names the image's file and says it is on the same disk" has "is a disk image whose file, $T/disk.dmg, is on the same disk as"
expect "  ... writes nothing there" empty_dir "$MNT/image-on-this-disk"

# An image inside the test image: its file is on the test image, whose own file is on this Mac's disk.
NMNT="$T/nested"
mkdir -p "$NMNT"
if hdiutil create -quiet -size 12m -fs APFS -volname VFNested "$MNT/nested.dmg" &&
   NESTDEV="$(hdiutil attach -nobrowse -noverify -mountpoint "$NMNT" "$MNT/nested.dmg" | awk 'NR == 1 { print $1 }')" &&
   [ -n "$NESTDEV" ]; then
  run "an image inside an image whose file is on this Mac's disk (real diskutil and hdiutil)" 2 PATH="$PATH" -- "$NMNT" --repo "$R"
  expect "  ... follows the images down to this Mac's disk" has "is a disk image whose file, $T/disk.dmg, is on the same disk as"
  run "an image inside an image on a USB drive (stand-in diskutil for the outer one)" 0 -- "$NMNT" --repo "$R"
  expect "  ... is accepted and backed up" has "OK    Group 1, the paid data"
  hdiutil detach "$NESTDEV" -force >/dev/null 2>&1 && NESTDEV=""
  rm -f "$MNT/nested.dmg"
else
  fail "could not make the image inside the test image"
fi

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
rm -rf "$MNT/Users"

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

MANY="$S/manyrepo"
mkdir -p "$MANY/nfl-weather/data/forward" "$MANY/cfb-weather/data/forward"
( cd "$MANY/nfl-weather/data/forward" && i=0 && while [ $i -lt 1000 ]; do printf 'x' > "r$i.csv"; i=$((i + 1)); done )
run "space for 1,000 one-byte records is counted in whole 4 KB blocks, twice (copy and snapshot)" 1 -- "$MNT/space" --repo "$MANY" --check
expect "  ... 1,000 x 2 x 4,096 bytes = 8.2 MB" has "A backup now writes about 8.2 MB"
rm -rf "$MANY"

# A stand-in diskutil that puts every volume on one physical disk, as two volumes of this Mac's own disk would be.
mkdir -p "$T/stub"
printf '#!/bin/sh\necho "   Part of Whole:             disk99"\n' > "$T/stub/diskutil"
chmod +x "$T/stub/diskutil"
mkdir -p "$MNT/volume2"
run "a destination on another volume of the same physical disk (stand-in diskutil)" 2 PATH="$T/stub:$PATH" -- "$MNT/volume2" --repo "$R"
expect "  ... says so" has "on the same physical disk (disk99) as"
expect "  ... writes nothing there" empty_dir "$MNT/volume2"

mkdir -p "$MNT/linked" "$S/elsewhere"
ln -s "$S/elsewhere" "$MNT/linked/value-finder-backup"
run "value-finder-backup on the drive is a link to this Mac's disk" 2 -- "$MNT/linked" --repo "$R"
expect "  ... says so" has "is a link to somewhere else"
expect "  ... writes nothing through the link" empty_dir "$S/elsewhere"
rm "$MNT/linked/value-finder-backup"
mkdir -p "$MNT/linked/value-finder-backup/nfl-weather/data"
ln -s "$S/elsewhere" "$MNT/linked/value-finder-backup/nfl-weather/data/forward"
run "a folder inside value-finder-backup is a link" 2 -- "$MNT/linked" --repo "$R"
expect "  ... names it" has "value-finder-backup/nfl-weather/data/forward is a link to somewhere else"
expect "  ... writes nothing through the link" empty_dir "$S/elsewhere"
rm -rf "$MNT/linked" "$S/elsewhere"

mkdir -p "$MNT/-bk"
cd "$MNT" || exit 1
run "a destination named -bk, without --" 2 -- -bk --repo "$R"
expect "  ... says to put it after --" has "goes after --"
run "a destination named -bk, after --" 0 -- --repo "$R" -- -bk
expect "  ... is backed up" has "Backup finished"
cd "$T" || exit 1
rm -rf "$MNT/-bk"

# ---- a first backup ----------------------------------------------------------------------------------------------------
D="$MNT/drive"
BK="$D/value-finder-backup"
mkdir -p "$D"
run "first backup" 0 -- "$D" --repo "$R"
expect "  ... group 1 OK" has "OK    Group 1, the paid data: 7 files and 2 links"
expect "  ... group 2 OK, snapshot included" has "OK    Group 2, the forward-test records: 6 files"
expect "  ... group 2 checked in the snapshot too" has "on the backup and in the snapshot forward-snapshots/"
expect "  ... group 3 copied" has "--    Group 3, slow to re-create: 3 files"
expect "  ... names the checkout and this Mac in its first line" has "Backing up $R on "
expect "  ... names the key files it left out" has "sharp-markets/data/raw/nba/prod.env"
expect "  ... including one five folders down" has "sharp-markets/data/raw/nba/deep/er/and/deeper/.env"
for n in "${CASEDAT[@]}"; do
  expect "  ... leaves out and names ${n##*/}" has "sharp-markets/data/raw/nba/$n"
done
expect "  ... and Secrets.json in the forecast archive (group 3)" has "~/.cache/value-finder/Secrets.json"
nkeys() { printf '%s\n' "$OUT" | awk '/^  Left out/ { on = 1; next } on && /^      / { n++; next } { on = 0 } END { print n + 0 }'; }
expect "  ... names every one of the $((${#CASED[@]} + 12)) key files, not only the first 10" [ "$(nkeys)" = $((${#CASED[@]} + 12)) ]
expect "  ... the manifest is copied" cmp -s "$MANIFEST" "$BK/sharp-markets/data/raw/_manifest/oddsapi_manifest.csv"
expect "  ... a file name with a space is copied" cmp -s "$NFLODDS/2025-09-07/odds week 1.json" "$BK/sharp-markets/data/raw/americanfootball_nfl/oddsapi/hist_odds/2025-09-07/odds week 1.json"
expect "  ... every oddsapi* folder is copied" cmp -s "$R/nfl-weather/data/raw/oddsapi_hist/h.json" "$BK/nfl-weather/data/raw/oddsapi_hist/h.json"
expect "  ... cfb-weather's oddsapi folder is copied" [ -f "$BK/cfb-weather/data/raw/oddsapi/live/x.json" ]
expect "  ... the ledger is copied" cmp -s "$R/nfl-weather/data/forward/ledger.csv" "$BK/nfl-weather/data/forward/ledger.csv"
expect "  ... the decision record is copied" cmp -s "$R/cfb-weather/data/forward/decisions.csv" "$BK/cfb-weather/data/forward/decisions.csv"
expect "  ... the forecast archive is copied" [ -f "$BK/home-cache/value-finder/mos/GFS/a.txt" ]
expect "  ... markets.duckdb is copied" cmp -s "$R/sharp-markets/data/markets.duckdb" "$BK/sharp-markets/data/markets.duckdb"
expect "  ... times are kept" [ "$(stat -f %m "$R/nfl-weather/data/forward/ledger.csv")" = "$(stat -f %m "$BK/nfl-weather/data/forward/ledger.csv")" ]
expect "  ... no key file anywhere on the backup, in any case" [ -z "$(find "$D" \( -iname '.env*' -o -iname '*.env' -o -iname env -o -iname kaggle.json -o -iname '*secret*' -o -iname '*credential*' -o -iname '*password*' -o -iname '*.key' -o -iname '*api_key*' -o -iname '*.pem' -o -iname 'id_*' -o -iname .netrc -o -iname '*token*.json' -o -iname 'service-account*' \))" ]
expect "  ... the key is nowhere on the backup" sh -c '! grep -rqF "$1" "$2"' - "$KEY" "$D"
expect "  ... no .venv, .git, .kaggle, .DS_Store or half-written .tmp" [ -z "$(find "$D" \( -name .venv -o -name .git -o -name .kaggle -o -name .DS_Store -o -name '*.tmp' \))" ]
expect "  ... a link is copied as a link" [ -L "$BK/sharp-markets/data/raw/nba/link_to_outside.txt" ]
expect "  ... pointing where it pointed" [ "$(readlink "$BK/sharp-markets/data/raw/nba/link_to_outside.txt")" = ../../../../../outside/secret.txt ]
expect "  ... a link to a folder is copied as a link" [ -L "$BK/sharp-markets/data/raw/nba/link_to_outside_folder" ]
expect "  ... what the links point to is not copied" sh -c '! grep -rqF OUTSIDE-CONTENT "$1"' - "$D"
expect "  ... folders not on the list are not copied" [ ! -e "$BK/nfl-weather/data/raw/weather" ]
expect "  ... one finished snapshot, none left incomplete" snaps_are "$BK" 1 0
SNAP1="$BK/forward-snapshots/$(ls "$BK/forward-snapshots")"
expect "  ... the snapshot holds the ledger" cmp -s "$R/nfl-weather/data/forward/ledger.csv" "$SNAP1/nfl-weather/data/forward/ledger.csv"
expect "  ... the snapshot has its list of SHA-256, one line per file" [ "$(wc -l < "$SNAP1/checksums.txt" | tr -d ' ')" = 6 ]
expect "  ... the log has one line, saying OK and the snapshot is verified" [ "$(grep -c ' OK .*verified' "$BK/backup-log.txt")" = 1 ]
expect "  ... the backup records where it came from" grep -qx "checkout: $R" "$BK/source.txt"
expect "  ... nothing was replaced" [ ! -e "$BK/replaced" ]

# ---- a second backup, after a file changed and files were added ------------------------------------------------------------
OLD_LEDGER="$(cat "$R/nfl-weather/data/forward/ledger.csv")"
OLD_MANIFEST="$(cat "$MANIFEST")"
printf '2,B\n' >> "$R/nfl-weather/data/forward/ledger.csv"
printf 'F2,c,d\n' >> "$MANIFEST"
mk "$NFLODDS/2025-09-14/k2.json" '{"b":2}'
mk "$R/cfb-weather/data/forward/forecasts/new.json" '{"new":1}'
mk "$R/nfl-weather/data/forward/alert_state.json" '{"g1":{}}'                  # the alert job rewrites it, smaller
run "second backup" 0 -- "$D" --repo "$R"
expect "  ... group 1 OK" has "OK    Group 1, the paid data: 8 files and 2 links"
expect "  ... group 2 OK" has "OK    Group 2, the forward-test records: 7 files"
expect "  ... the changed ledger is copied again under its name" cmp -s "$R/nfl-weather/data/forward/ledger.csv" "$BK/nfl-weather/data/forward/ledger.csv"
expect "  ... the grown manifest is copied again" cmp -s "$MANIFEST" "$BK/sharp-markets/data/raw/_manifest/oddsapi_manifest.csv"
expect "  ... a smaller alert_state.json is copied (it is rewritten, not added to)" cmp -s "$R/nfl-weather/data/forward/alert_state.json" "$BK/nfl-weather/data/forward/alert_state.json"
expect "  ... an added paid file is copied" [ -f "$BK/sharp-markets/data/raw/americanfootball_nfl/oddsapi/hist_odds/2025-09-14/k2.json" ]
expect "  ... an added forward file is copied" [ -f "$BK/cfb-weather/data/forward/forecasts/new.json" ]
expect "  ... says how many replaced files it kept" has "3 files on the backup were replaced or set aside; the backup's older copies are kept in value-finder-backup/replaced/"
REP="$(ls -d "$BK"/replaced/*)"
expect "  ... the old manifest is kept in replaced/" [ "$(cat "$REP/sharp-markets/data/raw/_manifest/oddsapi_manifest.csv")" = "$OLD_MANIFEST" ]
expect "  ... the old ledger is kept in replaced/" [ "$(cat "$REP/nfl-weather/data/forward/ledger.csv")" = "$OLD_LEDGER" ]
expect "  ... two snapshots" [ "$(nsnaps "$BK")" = 2 ]
expect "  ... the first snapshot still holds the ledger as it was" [ "$(cat "$SNAP1/nfl-weather/data/forward/ledger.csv")" = "$OLD_LEDGER" ]
SNAP2="$BK/forward-snapshots/$(ls "$BK/forward-snapshots" | tail -1)"
expect "  ... the second snapshot holds the new ledger" cmp -s "$R/nfl-weather/data/forward/ledger.csv" "$SNAP2/nfl-weather/data/forward/ledger.csv"
expect "  ... the log has two lines" [ "$(wc -l < "$BK/backup-log.txt" | tr -d ' ')" = 2 ]

# ---- --check ---------------------------------------------------------------------------------------------------------------
dest_state "$D" > "$T/dest-before"
run "--check on a good backup" 0 -- "$D" --repo "$R" --check
expect "  ... group 1 OK" has "OK    Group 1, the paid data"
expect "  ... group 2 OK" has "OK    Group 2, the forward-test records"
expect "  ... every snapshot checked against its list" has "OK    Snapshots of the forward-test records: 2 snapshots, 13 files; each file has the SHA-256 saved in its snapshot's list."
expect "  ... says it finished" has "Check finished: groups 1 and 2 and the snapshots match"
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
cp -p "$NFLODDS/2025-09-07/odds week 1.json" "$COPY"                         # the hub puts the good copy back

# ---- snapshots ---------------------------------------------------------------------------------------------------------------
SNAPFILE="$SNAP2/nfl-weather/data/forward/runs.csv"
cp -p "$SNAPFILE" "$T/runs.good"
printf 'X' | dd of="$SNAPFILE" bs=1 seek=1 conv=notrunc 2>/dev/null
touch -r "$T/runs.good" "$SNAPFILE"
run "--check after one byte of a file in an older snapshot was changed" 1 -- "$D" --repo "$R" --check
expect "  ... groups 1 and 2 OK" has "OK    Group 2, the forward-test records"
expect "  ... the snapshots FAIL, naming the file" has "forward-snapshots/$(basename "$SNAP2")/nfl-weather/data/forward/runs.csv: differs from the SHA-256 saved in the snapshot's list"
cp -p "$T/runs.good" "$SNAPFILE"
mv "$SNAP1/checksums.txt" "$T/checksums.good"
run "--check when a snapshot has no list of its files" 1 -- "$D" --repo "$R" --check
expect "  ... says never to restore from it" has "forward-snapshots/$(basename "$SNAP1"): has no list of its files (checksums.txt), so it may be incomplete: never restore from it"
mv "$T/checksums.good" "$SNAP1/checksums.txt"

# A snapshot cut short: a stand-in rsync that fails while copying cfb-weather into the new snapshot.
mkdir -p "$T/stub-cut"
cat > "$T/stub-cut/rsync" <<'STUB'
#!/bin/sh
case "$*" in *.incomplete-*cfb-weather/data/forward*) echo "rsync: stopped (stand-in)" >&2; exit 20 ;; esac
exec /usr/bin/rsync "$@"
STUB
chmod +x "$T/stub-cut/rsync"
NS="$(nsnaps "$BK")"
run "a backup whose snapshot is cut short" 1 PATH="$T/usb:$T/stub-cut:$PATH" -- "$D" --repo "$R"
expect "  ... says the copy into the snapshot stopped" has "cfb-weather/data/forward: the copy into the new snapshot stopped with an error (code 20"
expect "  ... the snapshot keeps its .incomplete- name" [ "$(nincomplete "$BK")" = 1 ]
expect "  ... and ls does not list it" [ "$(nsnaps "$BK")" = "$NS" ]
expect "  ... the log says it was not verified" grep -q 'FAIL .*snapshot left as forward-snapshots/.incomplete-' "$BK/backup-log.txt"
run "--check after that" 0 -- "$D" --repo "$R" --check
expect "  ... says the incomplete snapshot is not to be used" has "1 more snapshot in forward-snapshots, named .incomplete-..., did not finish or did not match: never restore from those."
run "the next backup" 0 -- "$D" --repo "$R"
expect "  ... makes a finished snapshot" [ "$(nsnaps "$BK")" = $((NS + 1)) ]

# ---- a file or folder on the backup that has become something else on this Mac ----------------------------------------------
mkdir -p "$S/moved"
mv "$MANIFEST" "$S/moved/oddsapi_manifest.csv"
ln -s "$S/moved/oddsapi_manifest.csv" "$MANIFEST"
mv "$NFLODDS/2025-09-07/k1.json" "$S/moved/k1.json"
ln -s "$S/moved/k1.json" "$NFLODDS/2025-09-07/k1.json"
K2="$NFLODDS/2025-09-14/k2.json"
cp -p "$K2" "$S/moved/k2.json"
rm "$K2"; mkdir "$K2"; mk "$K2/inside.json" '{}'
run "a backup after two paid files became links and one became a folder" 1 -- "$D" --repo "$R"
expect "  ... FAIL for the manifest" has "sharp-markets/data/raw/_manifest/oddsapi_manifest.csv: is a link on this Mac but a file on the backup"
expect "  ... FAIL for the paid file now a link" has "hist_odds/2025-09-07/k1.json: is a link on this Mac but a file on the backup"
expect "  ... FAIL for the paid file now a folder" has "hist_odds/2025-09-14/k2.json: is a folder on this Mac but a file on the backup"
expect "  ... the backup still holds the manifest as a file, unchanged" plain_same "$BK/sharp-markets/data/raw/_manifest/oddsapi_manifest.csv" "$S/moved/oddsapi_manifest.csv"
expect "  ... and the paid file now a link" plain_same "$BK/sharp-markets/data/raw/americanfootball_nfl/oddsapi/hist_odds/2025-09-07/k1.json" "$S/moved/k1.json"
expect "  ... and the paid file now a folder" plain_same "$BK/sharp-markets/data/raw/americanfootball_nfl/oddsapi/hist_odds/2025-09-14/k2.json" "$S/moved/k2.json"
run "--check after that" 1 -- "$D" --repo "$R" --check
expect "  ... still FAIL for the link" has "k1.json: is a link on this Mac but a file on the backup"
BKODDS="$BK/sharp-markets/data/raw/americanfootball_nfl/oddsapi/hist_odds"
run "the hub's decision: --accept-changes" 0 -- "$D" --repo "$R" --accept-changes
LASTREP="$(ls -d "$BK"/replaced/* | tail -1)"
expect "  ... the backup's manifest file is kept in replaced/" cmp -s "$S/moved/oddsapi_manifest.csv" "$LASTREP/sharp-markets/data/raw/_manifest/oddsapi_manifest.csv"
expect "  ... and its k1.json" cmp -s "$S/moved/k1.json" "$LASTREP/sharp-markets/data/raw/americanfootball_nfl/oddsapi/hist_odds/2025-09-07/k1.json"
expect "  ... and its k2.json" cmp -s "$S/moved/k2.json" "$LASTREP/sharp-markets/data/raw/americanfootball_nfl/oddsapi/hist_odds/2025-09-14/k2.json"
expect "  ... the main copy now matches this Mac: a link and a folder" link_and_folder "$BKODDS/2025-09-07/k1.json" "$BKODDS/2025-09-14/k2.json"
rm "$MANIFEST" "$NFLODDS/2025-09-07/k1.json"; rm -r "$K2"
mv "$S/moved/oddsapi_manifest.csv" "$MANIFEST"; mv "$S/moved/k1.json" "$NFLODDS/2025-09-07/k1.json"; mv "$S/moved/k2.json" "$K2"
run "a backup once the files are back" 1 -- "$D" --repo "$R"
expect "  ... the links on the backup are replaced by the files (a link holds no data)" plain "$BKODDS/2025-09-07/k1.json"
expect "  ... but the folder on the backup waits for a decision" has "k2.json: is a file on this Mac but a folder on the backup"
run "--accept-changes once more" 0 -- "$D" --repo "$R" --accept-changes
run "--check after that" 0 -- "$D" --repo "$R" --check

FC="$R/nfl-weather/data/forward/forecasts"
mv "$FC" "$S/moved/forecasts"
printf 'not a folder' > "$FC"
run "a backup after a forward folder became a file" 1 -- "$D" --repo "$R"
expect "  ... FAIL for it" has "nfl-weather/data/forward/forecasts: is a file on this Mac but a folder on the backup"
expect "  ... the backup keeps the folder and its files" [ -f "$BK/nfl-weather/data/forward/forecasts/f1.json" ]
rm "$FC"; mv "$S/moved/forecasts" "$FC"

DUCK="$R/sharp-markets/data/markets.duckdb"
mv "$DUCK" "$S/moved/markets.duckdb"; ln -s "$S/moved/markets.duckdb" "$DUCK"
run "a backup after markets.duckdb became a link" 1 -- "$D" --repo "$R"
expect "  ... FAIL for group 3, naming it" has "sharp-markets/data/markets.duckdb: is a link on this Mac but a file on the backup; not copied"
expect "  ... the backup keeps the file" plain_same "$BK/sharp-markets/data/markets.duckdb" "$S/moved/markets.duckdb"
run "the same with --accept-changes" 0 -- "$D" --repo "$R" --accept-changes
expect "  ... keeps the backup's file in replaced/" cmp -s "$S/moved/markets.duckdb" "$(ls -d "$BK"/replaced/* | tail -1)/sharp-markets/data/markets.duckdb"
rm "$DUCK"; mv "$S/moved/markets.duckdb" "$DUCK"
run "a backup once it is back" 0 -- "$D" --repo "$R"
expect "  ... the backup has the file again" cmp -s "$DUCK" "$BK/sharp-markets/data/markets.duckdb"

# markets.duckdb on the backup replaced, by hand, with a link to a folder on this Mac's disk.
mkdir -p "$T/outside-dir"
mv "$BK/sharp-markets/data/markets.duckdb" "$T/duck.from-backup"
ln -s "$T/outside-dir" "$BK/sharp-markets/data/markets.duckdb"
printf 'more' >> "$DUCK"
run "a backup when markets.duckdb on the backup is a link to a folder elsewhere" 0 -- "$D" --repo "$R"
expect "  ... writes nothing through the link" empty_dir "$T/outside-dir"
expect "  ... the backup holds this Mac's markets.duckdb, as a file" plain_same "$BK/sharp-markets/data/markets.duckdb" "$DUCK"
rm -rf "$T/outside-dir" "$T/duck.from-backup"

# ---- a file that got smaller, and files gone from this Mac -------------------------------------------------------------------
cp -p "$MANIFEST" "$T/manifest.good"
printf 'pull,requested,returned\n' > "$MANIFEST"
run "--check after the manifest was cut to its header line" 1 -- "$D" --repo "$R" --check
expect "  ... FAIL: smaller here, not \"new or changed\"" has "_manifest/oddsapi_manifest.csv: is smaller on this Mac (24 bytes) than on the backup"
run "a backup after that" 1 -- "$D" --repo "$R"
expect "  ... FAIL again" has "_manifest/oddsapi_manifest.csv: is smaller on this Mac (24 bytes) than on the backup"
expect "  ... the backup keeps the larger copy" cmp -s "$T/manifest.good" "$BK/sharp-markets/data/raw/_manifest/oddsapi_manifest.csv"
run "the hub's decision: --accept-changes" 0 -- "$D" --repo "$R" --accept-changes
expect "  ... copies the smaller one" cmp -s "$MANIFEST" "$BK/sharp-markets/data/raw/_manifest/oddsapi_manifest.csv"
expect "  ... and keeps the larger one in replaced/" cmp -s "$T/manifest.good" "$(ls -d "$BK"/replaced/* | tail -1)/sharp-markets/data/raw/_manifest/oddsapi_manifest.csv"
cp -p "$T/manifest.good" "$MANIFEST"
run "the next backup, with the manifest back" 0 -- "$D" --repo "$R"

L="$R/nfl-weather/data/forward/ledger.csv"
cp -p "$L" "$T/ledger.good"; : > "$L"
run "a backup after the nfl ledger was emptied" 1 -- "$D" --repo "$R"
expect "  ... FAIL for it" has "nfl-weather/data/forward/ledger.csv: is smaller on this Mac (0 bytes) than on the backup"
expect "  ... the backup keeps the full ledger" cmp -s "$T/ledger.good" "$BK/nfl-weather/data/forward/ledger.csv"
cp -p "$T/ledger.good" "$L"

mkdir -p "$S/gone"
mv "$NFLODDS/2025-09-07/k1.json" "$R/nfl-weather/data/forward/runs.csv" "$S/gone/"
mv "$MANIFEST" "$S/gone/manifest.csv"
run "--check after a paid file, the manifest and runs.csv were deleted here" 1 -- "$D" --repo "$R" --check
expect "  ... FAIL for the paid file" has "hist_odds/2025-09-07/k1.json: is on the backup but no longer on this Mac"
expect "  ... FAIL for the manifest" has "_manifest/oddsapi_manifest.csv: is on the backup but no longer on this Mac"
expect "  ... FAIL for runs.csv" has "nfl-weather/data/forward/runs.csv: is on the backup but no longer on this Mac"
run "a backup after that" 1 -- "$D" --repo "$R"
expect "  ... FAIL too" has "k1.json: is on the backup but no longer on this Mac"
expect "  ... the backup keeps them" [ -f "$BKODDS/2025-09-07/k1.json" ]
run "the hub's decision that they were removed on purpose: --accept-changes" 0 -- "$D" --repo "$R" --accept-changes
LASTREP="$(ls -d "$BK"/replaced/* | tail -1)"
expect "  ... moves them into replaced/, keeping them" same2 "$S/gone/k1.json" "$LASTREP/sharp-markets/data/raw/americanfootball_nfl/oddsapi/hist_odds/2025-09-07/k1.json" "$S/gone/runs.csv" "$LASTREP/nfl-weather/data/forward/runs.csv"
expect "  ... out of the main copy" [ ! -e "$BKODDS/2025-09-07/k1.json" ]
run "--check after that" 0 -- "$D" --repo "$R" --check
mv "$S/gone/k1.json" "$NFLODDS/2025-09-07/"; mv "$S/gone/runs.csv" "$R/nfl-weather/data/forward/"; mv "$S/gone/manifest.csv" "$MANIFEST"
run "a backup once they are back" 0 -- "$D" --repo "$R"

mv "$R/cfb-weather/data/raw/oddsapi" "$S/oddsapi.moved"
run "--check when a paid-data folder is gone from this Mac" 1 -- "$D" --repo "$R" --check
expect "  ... says it is not on this Mac, but the backup has it" has "cfb-weather/data/raw/oddsapi: not on this Mac, but the backup has it"
run "a backup after that" 1 -- "$D" --repo "$R"
expect "  ... FAIL for it" has "cfb-weather/data/raw/oddsapi: not on this Mac, but the backup has it"
expect "  ... the backup keeps it" [ -f "$BK/cfb-weather/data/raw/oddsapi/live/x.json" ]
run "the hub's decision that the folder was removed on purpose: --accept-changes" 0 -- "$D" --repo "$R" --accept-changes
expect "  ... says it moved the backup's copy into replaced/" has "cfb-weather/data/raw/oddsapi: not on this Mac, so the backup's copy was moved into value-finder-backup/replaced/"
LASTREP="$(ls -d "$BK"/replaced/* | tail -1)"
expect "  ... which keeps it" cmp -s "$S/oddsapi.moved/live/x.json" "$LASTREP/cfb-weather/data/raw/oddsapi/live/x.json"
expect "  ... out of the main copy" [ ! -e "$BK/cfb-weather/data/raw/oddsapi" ]
run "a backup after that" 0 -- "$D" --repo "$R"
mv "$S/oddsapi.moved" "$R/cfb-weather/data/raw/oddsapi"
run "a backup once the folder is back" 0 -- "$D" --repo "$R"
expect "  ... copies it again" [ -f "$BK/cfb-weather/data/raw/oddsapi/live/x.json" ]

# rsync's own leftovers: ".NAME." and 10 letters and digits (the rsync of macOS) or 6 (another rsync), beside a NAME
# that is on this Mac.
HO="$BK/sharp-markets/data/raw/americanfootball_nfl/oddsapi/hist_odds/2025-09-07"
mk "$HO/.k1.json.K60GoyT0AP" 'part of a copy'
mk "$HO/.k1.json.a1B2c3" 'part of a copy'
run "--check with partial copies a stopped backup left on the drive" 0 -- "$D" --repo "$R" --check
expect "  ... lists one as harmless" has "hist_odds/2025-09-07/.k1.json.K60GoyT0AP: a partial copy that a stopped backup left (harmless: restores skip it)"
expect "  ... and the other" has "hist_odds/2025-09-07/.k1.json.a1B2c3: a partial copy that a stopped backup left"
# Real files whose names only look like that: gone from this Mac, they are a FAIL, not "harmless".
mk "$RAW/nba/kalshi/.index.parquet" 'an index'
mk "$R/nfl-weather/data/forward/.decisions.backup" 'a copy of the decisions'
touch -t 202609010000 "$RAW/nba/kalshi/.index.parquet" "$R/nfl-weather/data/forward/.decisions.backup"
run "a backup of two dot files ending in 7 and 6 letters" 0 -- "$D" --repo "$R"
mk "$HO/.k3.json.K60GoyT0AP" 'no k3.json here'
mkdir -p "$S/gone2"
mv "$RAW/nba/kalshi/.index.parquet" "$R/nfl-weather/data/forward/.decisions.backup" "$S/gone2/"
run "--check after they were deleted here" 1 -- "$D" --repo "$R" --check
expect "  ... FAIL for .index.parquet, not \"harmless\"" has "sharp-markets/data/raw/nba/kalshi/.index.parquet: is on the backup but no longer on this Mac"
expect "  ... FAIL for .decisions.backup" has "nfl-weather/data/forward/.decisions.backup: is on the backup but no longer on this Mac"
expect "  ... FAIL for a leftover-looking name with no such file beside it" has "2025-09-07/.k3.json.K60GoyT0AP: is on the backup but no longer on this Mac"
run "a backup after that" 1 -- "$D" --repo "$R"
expect "  ... FAIL too" has ".index.parquet: is on the backup but no longer on this Mac"
run "--accept-changes" 0 -- "$D" --repo "$R" --accept-changes
LASTREP="$(ls -d "$BK"/replaced/* | tail -1)"
expect "  ... keeps the two files in replaced/" same2 "$S/gone2/.index.parquet" "$LASTREP/sharp-markets/data/raw/nba/kalshi/.index.parquet" "$S/gone2/.decisions.backup" "$LASTREP/nfl-weather/data/forward/.decisions.backup"
expect "  ... and moves the partial copies there too" [ -f "$LASTREP/sharp-markets/data/raw/americanfootball_nfl/oddsapi/hist_odds/2025-09-07/.k1.json.K60GoyT0AP" ]
expect "  ... out of the main copy" [ -z "$(ls -A "$HO" | grep '^\.')" ]
run "--check after that" 0 -- "$D" --repo "$R" --check
expect "  ... lists no partial copy" hasnt "partial copy"

NLNAME="$RAW/nba/new
line.json"
mk "$NLNAME" '{}'
touch -t 202609010000 "$NLNAME"
run "a backup with a line break in a file name" 1 -- "$D" --repo "$R"
expect "  ... names it plainly, with ? for the break" has "sharp-markets/data/raw/nba/new?line.json: has a line break in its name, which this script can't check"
expect "  ... counts the other files right" has "(8 files and 2 links"
rm "$NLNAME"

# ---- another checkout or another Mac, writing to the same backup ------------------------------------------------------------
R2="$S/repo2"
cp -Rp "$R" "$R2" 2>/dev/null                                           # all but the unreadable .env.local
printf 'id,rule\n' > "$R2/nfl-weather/data/forward/ledger.csv"             # this older copy has fewer rows
run "a backup from another checkout" 2 -- "$D" --repo "$R2"
expect "  ... is refused, naming both" has2 "This backup was last made from" "checkout $R2"
run "--check from it" 1 -- "$D" --repo "$R2" --check
expect "  ... runs, with a note" has "Note: This backup was last made from"
run "the same with --new-source" 1 -- "$D" --repo "$R2" --new-source
expect "  ... still does not replace the longer ledger" has "nfl-weather/data/forward/ledger.csv: is smaller on this Mac"
expect "  ... which the backup keeps" cmp -s "$T/ledger.good" "$BK/nfl-weather/data/forward/ledger.csv"
expect "  ... and records the new source" grep -qx "checkout: $R2" "$BK/source.txt"
run "back to the first checkout" 0 -- "$D" --repo "$R" --new-source
rm -rf "$R2"
run "a backup from another Mac (stand-in ioreg)" 2 PATH="$T/usb:$T/othermac:$PATH" -- "$D" --repo "$R"
expect "  ... is refused, naming the other Mac" has2 "This backup was last made from" "(Mac 00000000, checkout"

# ---- a record written while a backup runs ------------------------------------------------------------------------------------
# A stand-in rsync appends to the cfb-weather ledger right after it copies that folder. This run changes the source on
# purpose, so it is not wrapped in run().
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
OUT="$(env -u MARKETS_DATA_DIR -u MARKETS_ROOT HOME="$H" USB_NODES="$USB_NODES" PATH="$T/usb:$T/stub-rsync:$PATH" \
       FLAG="$T/stub-rsync/done" TARGET="$R/cfb-weather/data/forward/ledger.csv" "$SCRIPT" "$D4" --repo "$R" 2>&1)"
STATUS=$?
expect "a record written while a backup runs: exit status 1" [ "$STATUS" = 1 ]
expect "  ... names it and says it changed while the backup ran" has "cfb-weather/data/forward/ledger.csv: differs (size), changed on this Mac while this ran"
expect "  ... the stand-in did write during the run" [ -e "$T/stub-rsync/done" ]
expect "  ... no key in the output" hasnt "$KEY"
[ -z "${VERBOSE:-}" ] || printf '%s\n' "$OUT" | sed 's/^/      | /'
run "the same backup run again" 0 -- "$D4" --repo "$R"
expect "  ... group 2 OK" has "OK    Group 2, the forward-test records"

# ---- folders not created yet -------------------------------------------------------------------------------------------------
D5="$MNT/drive5"
mkdir -p "$D5"
mv "$R/cfb-weather/data/forward" "$S/cfb-forward.moved"
run "a backup before cfb-weather has any forward records" 0 -- "$D5" --repo "$R"
expect "  ... says so plainly" has "not created yet; nothing to copy"
expect "  ... no FAIL" hasnt "FAIL"
mv "$S/cfb-forward.moved" "$R/cfb-weather/data/forward"

EMPTY="$S/new-data-folder"
mkdir -p "$EMPTY"
D6="$MNT/drive6"
mkdir -p "$D6"
run "a backup with MARKETS_DATA_DIR at a new, empty data folder" 0 MARKETS_DATA_DIR="$EMPTY" -- "$D6" --repo "$R"
expect "  ... says its raw folder is not created yet" has "$EMPTY/raw"
expect "  ... no FAIL" hasnt "FAIL"
rm -rf "$EMPTY"

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
run "the same backup without MARKETS_DATA_DIR" 2 -- "$D3" --repo "$R"
expect "  ... is refused: the backup came from another data folder" has "sharp-markets data folder $ALT"

# ---- two runs in the same second (a clock that repeats itself) --------------------------------------------------------------
# A stand-in date gives every run the same start time, so every run has the same name. Each must still keep what it
# replaces in a folder of its own.
mkdir -p "$T/fixdate"
cat > "$T/fixdate/date" <<'STUB'
#!/bin/sh
[ "$*" = "+%s" ] && { echo 1790000000; exit 0; }
exec /bin/date "$@"
STUB
chmod +x "$T/fixdate/date"
D8="$MNT/drive8"
BK8="$D8/value-finder-backup"
mkdir -p "$D8"
cp -p "$MANIFEST" "$T/manifest.v1"
run "a backup, before two runs with the same start time" 0 -- "$D8" --repo "$R"
printf 'F8,x,y\n' >> "$MANIFEST"; cp -p "$MANIFEST" "$T/manifest.v2"
run "a first run at a repeated time" 0 PATH="$T/usb:$T/fixdate:$PATH" -- "$D8" --repo "$R"
printf 'F9,x,y\n' >> "$MANIFEST"
run "a second run at the same time" 0 PATH="$T/usb:$T/fixdate:$PATH" -- "$D8" --repo "$R"
expect "  ... says it kept the older copy in a folder with -2 added" has "kept in value-finder-backup/replaced/2026-09-21T141320Z-2/"
M8=sharp-markets/data/raw/_manifest/oddsapi_manifest.csv
expect "  ... the first version is still kept" cmp -s "$T/manifest.v1" "$BK8/replaced/2026-09-21T141320Z/$M8"
expect "  ... and the second" cmp -s "$T/manifest.v2" "$BK8/replaced/2026-09-21T141320Z-2/$M8"
expect "  ... and the main copy has the third" cmp -s "$MANIFEST" "$BK8/$M8"
K8="$NFLODDS/2025-09-14/k2.json"
mv "$K8" "$T/k2.v1"
run "--accept-changes at the same time again, after k2.json was removed here" 0 PATH="$T/usb:$T/fixdate:$PATH" -- "$D8" --repo "$R" --accept-changes
mk "$K8" '{"b":"version 2"}'
run "a backup of a new k2.json" 0 -- "$D8" --repo "$R"
mv "$K8" "$T/k2.v2"
run "--accept-changes at the same time once more, after it was removed again" 0 PATH="$T/usb:$T/fixdate:$PATH" -- "$D8" --repo "$R" --accept-changes
K8R=sharp-markets/data/raw/americanfootball_nfl/oddsapi/hist_odds/2025-09-14/k2.json
expect "  ... both versions of k2.json are kept, each in its own folder" same2 "$T/k2.v1" "$BK8/replaced/2026-09-21T141320Z-3/$K8R" "$T/k2.v2" "$BK8/replaced/2026-09-21T141320Z-4/$K8R"
mv "$T/k2.v1" "$K8"; cp -p "$T/manifest.v1" "$MANIFEST"; touch -r "$T/manifest.v1" "$MANIFEST"
rm -rf "$D8"

# ---- group 3: what a backup replaces is kept too ------------------------------------------------------------------------
D9="$MNT/drive9"
BK9="$D9/value-finder-backup"
mkdir -p "$D9"
FORECAST="$H/.cache/value-finder/mos/GFS/a.txt"
cp -p "$DUCK" "$T/duck.good"; cp -p "$FORECAST" "$T/forecast.good"
mk "$R/sharp-markets/data/markets.duckdb.wal" 'the write-ahead file of this markets.duckdb'
run "a backup with markets.duckdb and its write-ahead file" 0 -- "$D9" --repo "$R"
expect "  ... copies the write-ahead file" [ -f "$BK9/sharp-markets/data/markets.duckdb.wal" ]
rm "$R/sharp-markets/data/markets.duckdb.wal"
printf 'D' > "$DUCK"                                  # cut short
: > "$FORECAST"                                       # emptied
run "a backup after markets.duckdb was cut short and a forecast file emptied" 0 -- "$D9" --repo "$R"
LASTREP="$(ls -d "$BK9"/replaced/* | tail -1)"
expect "  ... keeps the good markets.duckdb in replaced/" cmp -s "$T/duck.good" "$LASTREP/sharp-markets/data/markets.duckdb"
expect "  ... and the good forecast file" cmp -s "$T/forecast.good" "$LASTREP/home-cache/value-finder/mos/GFS/a.txt"
wal_aside() { [ -f "$LASTREP/sharp-markets/data/markets.duckdb.wal" ] && [ ! -e "$BK9/sharp-markets/data/markets.duckdb.wal" ]; }
expect "  ... moves the old write-ahead file there, away from the new markets.duckdb" wal_aside
expect "  ... says so" has "sharp-markets/data/markets.duckdb.wal: not on this Mac, so the backup's copy was moved into value-finder-backup/replaced/"
cp -p "$T/duck.good" "$DUCK"; cp -p "$T/forecast.good" "$FORECAST"
rm -rf "$D9"

# ---- a path longer than macOS allows -------------------------------------------------------------------------------------
# rsync stops on it; the script must name the file, not leave it out of its count and comparison without a word.
DEEP="$T/deeprepo"
mkdir -p "$DEEP/nfl-weather/data/forward" "$DEEP/cfb-weather/data/forward" "$DEEP/sharp-markets/data/raw/deep"
mk "$DEEP/sharp-markets/data/raw/short.json" '{}'
SEG="$(printf 'd%.0s' $(seq 1 120))"
( cd "$DEEP/sharp-markets/data/raw/deep" && for x in 1 2 3 4 5 6 7 8 9 10 11 12; do mkdir "$SEG$x" && cd "$SEG$x" || exit 1; done
  printf 'paid' > paid130.json )
D10="$MNT/drive10"
mkdir -p "$D10"
run "a backup with a paid file whose path is over 1,024 characters" 1 -- "$D10" --repo "$DEEP"
expect "  ... FAIL naming the file" has "/paid130.json: could not be read on this Mac (File name too long)"
expect "  ... says the count is short" has "part of it could not be read, so these numbers are short"
rm -rf "$DEEP" "$D10"

# ---- an ExFAT drive, where macOS keeps extra information in ._ files -------------------------------------------------------
XMNT="$T/exfat"
mkdir -p "$XMNT"
if hdiutil create -quiet -size 16m -fs ExFAT -volname VFExFAT "$T/exfat.dmg" &&
   XATTACH="$(hdiutil attach -nobrowse -noverify -mountpoint "$XMNT" "$T/exfat.dmg")" &&
   EXDEV="$(printf '%s\n' "$XATTACH" | awk 'NR == 1 { print $1 }')" && [ -n "$EXDEV" ]; then
  USB_NODES="$USB_NODES$(printf '%s\n' "$XATTACH" | awk '$1 ~ /^\/dev\/disk/ { sub(/^\/dev\//, "", $1); printf "%s ", $1 }')"
  run "a backup to an ExFAT drive" 0 -- "$XMNT" --repo "$R"
  xattr -w com.example.note yes "$XMNT/value-finder-backup/$M8"          # makes a ._ file beside it
  xattr -w com.example.note yes "$XMNT/value-finder-backup/nfl-weather/data/forward/ledger.csv"
  expect "  ... (the test made ._ files on it)" [ -e "$XMNT/value-finder-backup/sharp-markets/data/raw/_manifest/._oddsapi_manifest.csv" ]
  run "--check on the ExFAT drive" 0 -- "$XMNT" --repo "$R" --check
  expect "  ... does not call the ._ files missing here" hasnt "/._"
  run "another backup to it" 0 -- "$XMNT" --repo "$R"
  hdiutil detach "$EXDEV" -force >/dev/null 2>&1 && EXDEV=""
else
  fail "could not make the ExFAT test disk"
fi

# ---- the restore commands on ops/BACKUP.md ------------------------------------------------------------------------------------
# Into a copy of the checkout: the paid data from the backup (skipping a partial copy), then --check; the forward
# records from the latest snapshot, then the comparison the page gives.
R7="$S/repo7"
cp -Rp "$R" "$R7" 2>/dev/null
D7="$MNT/drive7"
mkdir -p "$D7"
run "a backup of the copy" 0 -- "$D7" --repo "$R7"
BK7="$D7/value-finder-backup"
mk "$BK7/sharp-markets/data/raw/nba/kalshi/2026-01-05/.c.parquet.a1B2c3" 'part of a copy'
rm "$R7/sharp-markets/data/raw/americanfootball_nfl/oddsapi/hist_odds/2025-09-07/k1.json"
printf 'damaged' > "$R7/sharp-markets/data/raw/_manifest/oddsapi_manifest.csv"
MD="$( cd "$R7/sharp-markets/data" &&
  mv raw "raw.damaged-$(date +%Y%m%d-%H%M%S)" && [ ! -e raw ] && echo "Moved aside." &&
  rsync -a --exclude='.*.??????' --exclude='.*.??????????' "$BK7/sharp-markets/data/raw/" raw/ )"
expect "restoring the paid data: the damaged folder is moved aside" [ "$MD" = "Moved aside." ]
expect "  ... under a dated name, holding the damaged manifest" grep -qx damaged "$R7"/sharp-markets/data/raw.damaged-*/_manifest/oddsapi_manifest.csv
expect "  ... the restore skips the partial copy" [ ! -e "$R7/sharp-markets/data/raw/nba/kalshi/2026-01-05/.c.parquet.a1B2c3" ]
run "--check after restoring the paid data" 0 -- "$D7" --repo "$R7" --check
expect "  ... the lost file is back" [ -f "$R7/sharp-markets/data/raw/americanfootball_nfl/oddsapi/hist_odds/2025-09-07/k1.json" ]
# markets.duckdb, twice: the second restore must not replace the first damaged copy.
restore_duck() {
  ( cd "$R7/sharp-markets/data" && t=$(date +%Y%m%d-%H%M%S) && [ ! -e "markets.duckdb.damaged-$t" ] &&
    mv markets.duckdb "markets.duckdb.damaged-$t" &&
    { [ ! -e markets.duckdb.wal ] || mv markets.duckdb.wal "markets.duckdb.wal.damaged-$t"; } && echo "Moved aside." &&
    rsync -a "$BK7"/sharp-markets/data/markets.duckdb* ./ )
}
printf 'DAMAGED-ONCE' > "$R7/sharp-markets/data/markets.duckdb"
printf 'an old write-ahead file' > "$R7/sharp-markets/data/markets.duckdb.wal"
MD="$(restore_duck)"
expect "restoring markets.duckdb with its two commands" cmp -s "$R/sharp-markets/data/markets.duckdb" "$R7/sharp-markets/data/markets.duckdb"
expect "  ... moves this Mac's write-ahead file aside too" [ ! -e "$R7/sharp-markets/data/markets.duckdb.wal" ]
sleep 1
printf 'DAMAGED-AGAIN' > "$R7/sharp-markets/data/markets.duckdb"
MD="$(restore_duck)"
expect "  ... a second restore keeps both damaged copies, each under its own name" [ "$(cat "$R7"/sharp-markets/data/markets.duckdb.damaged-*)" = "DAMAGED-ONCEDAMAGED-AGAIN" ]
SNAP7="$BK7/forward-snapshots/$(ls "$BK7/forward-snapshots" | tail -1)"
printf '9,B\n' >> "$R7/nfl-weather/data/forward/ledger.csv"                    # the damage
F7="$R7/nfl-weather/data"
rsync -a "$SNAP7/nfl-weather/data/forward/" "$F7/forward.restored/"
CMP="$(cd "$F7" && diff -rq "$SNAP7/nfl-weather/data/forward" forward.restored && echo "The restored folder matches the snapshot.")"
expect "restoring the forward records from a snapshot into forward.restored, then comparing both ways" [ "$CMP" = "The restored folder matches the snapshot." ]
rm "$F7/forward.restored/forecasts/f1.json"
CMP="$(cd "$F7" && diff -rq "$SNAP7/nfl-weather/data/forward" forward.restored && echo "The restored folder matches the snapshot.")"
caught() { [ "$CMP" != "The restored folder matches the snapshot." ] && printf '%s' "$CMP" | grep -q "f1.json"; }
expect "  ... an incomplete restore is caught" caught
cp -p "$SNAP7/nfl-weather/data/forward/forecasts/f1.json" "$F7/forward.restored/forecasts/f1.json"
SW="$(cd "$F7" && mv forward "forward.damaged-$(date +%Y%m%d-%H%M%S)" && [ ! -e forward ] && mv forward.restored forward && echo "Restored.")"
expect "  ... the swap puts the restored folder in place" same2 "$SNAP7/nfl-weather/data/forward/ledger.csv" "$F7/forward/ledger.csv" "$SNAP7/nfl-weather/data/forward/runs.csv" "$F7/forward/runs.csv"
expect "  ... and keeps the damaged one under a dated name" grep -q '^9,B$' "$F7"/forward.damaged-*/ledger.csv
# If a job had made a new forward/ in between, the swap stops instead of moving the restored folder inside it.
rsync -a "$SNAP7/nfl-weather/data/forward/" "$F7/forward.restored/"
SW="$(cd "$F7" && mv forward "forward.damaged-$(date +%Y%m%d-%H%M%S)-b" && mkdir forward && printf 'row 5\n' > forward/ledger.csv &&
      [ ! -e forward ] && mv forward.restored forward && echo "Restored.")"
swap_stopped() { [ -z "$SW" ] && [ -d "$F7/forward.restored" ] && grep -qx 'row 5' "$F7/forward/ledger.csv"; }
expect "  ... the swap stops when forward/ was made again in between, leaving both" swap_stopped
chmod -R u+rwx "$R7"; rm -rf "$R7"

echo
echo "$PASSED passed, $FAILED failed."
[ "$FAILED" -eq 0 ]
