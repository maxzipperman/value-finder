#!/bin/bash
# Back up the paid odds data and the forward-test records to another disk. The owner's page: ops/BACKUP.md.
#
#   ops/backup_data.sh DEST                   copy into DEST/value-finder-backup/, then compare groups 1 and 2 both ways
#   ops/backup_data.sh DEST --check           compare only, and check every snapshot: copy nothing and write nothing
#   ops/backup_data.sh DEST --repo PATH       back up that checkout (default: the one this script is in)
#   ops/backup_data.sh DEST --allow-cloud     allow a folder that iCloud Drive, Dropbox, Google Drive or OneDrive syncs
#   ops/backup_data.sh DEST --new-source      allow a backup last made from another Mac, checkout or data folder
#   ops/backup_data.sh DEST --accept-changes  the hub's decision that this Mac's files are right (see below)
#   ops/backup_data.sh -- DEST                a destination whose name starts with a dash goes after --
#
# What it copies, most important first:
#   group 1, the paid data: the sharp-markets data folder's raw/ (the folder MARKETS_DATA_DIR names when it is set, as
#            sharp-markets/src/markets/settings.py reads it), each weather project's data/raw/oddsapi* folders,
#            the complete football acquisition state parent, frozen bundles/reuse and non-secret run evidence
#   group 2, the forward-test records: each weather project's data/forward/, also kept at every run as a dated
#            snapshot, DEST/value-finder-backup/forward-snapshots/<UTC date and time>/, with a SHA-256 list of its files
#   group 3, slow to re-create: ~/.cache/value-finder (the forecast archive) and sharp-markets' markets.duckdb
# Never copied: names that look like key files, in upper or lower case (.env*, *.env, env, .netrc, kaggle.json, .kaggle,
# *.pem, *.p12, *.key, id_rsa*, id_ed25519*, *secret*, *credential*, *password*, *api_key*, *api-key*, *apikey*,
# *token*.json, service-account*.json; each one found is named in the output, and none is ever opened), .venv and .git
# folders, Finder's .DS_Store and ._ files, and half-written *.tmp files. Links are copied as links and never followed.
# The source is only read. Nothing on the destination is ever deleted. In all three groups, a file the copy replaces is
# first kept in value-finder-backup/replaced/<UTC date and time>/ (a folder name no earlier run used). Three kinds of
# change are each a FAIL, and the backup keeps its own copy, until the hub decides: a file or folder on the backup that
# is something else here (a link, say; this holds in group 3 too), a file of groups 1 and 2 that got smaller here
# (except the alert jobs' *_state.json files, which are rewritten), and a file or folder of groups 1 and 2 on the backup
# that is gone from here. --accept-changes is that decision: the backup's copies (and any partial copies a stopped
# backup left) are moved into replaced/<UTC date and time>/ (never deleted), and this Mac's files are copied.
# A backup last made from another Mac, checkout or sharp-markets data folder is refused (--new-source allows it).
# A snapshot is written as forward-snapshots/.incomplete-<time> and gets its real name only once it matches this Mac.
# After copying, every file of groups 1 and 2 is compared on both sides by size and SHA-256, both ways. --check makes
# the same comparison (a file written on this Mac since the last backup began is listed as new, not a FAIL) and checks
# every snapshot against its list.
# Exit status: 0 when everything compared matches, 1 on any FAIL, 2 when it refuses to start.
# Plain bash 3.2 and the tools macOS ships (rsync, find, stat, df, diskutil, hdiutil, ioreg, sha256sum or shasum).
set -u
set -o pipefail
export LC_ALL=C
NL=$'\n'

usage() { sed -n '4,10p' "$0" | sed 's/^# *//'; }

refuse() {
  printf '%s\n' "$1" >&2
  printf '%s\n' "Stopped before copying anything. ops/BACKUP.md explains each rule." >&2
  exit 2
}

DEST="" CHECK=0 ALLOW_CLOUD=0 REPO="" NEW_SOURCE=0 ACCEPT=0
set_dest() {
  [ -z "$DEST" ] || refuse "Give one destination, not two ($DEST and $1). Put quotes around a name with spaces."
  DEST="$1"
}
while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECK=1 ;;
    --allow-cloud) ALLOW_CLOUD=1 ;;
    --new-source) NEW_SOURCE=1 ;;
    --accept-changes) ACCEPT=1 ;;
    --repo) [ $# -ge 2 ] || refuse "--repo needs a folder: ops/backup_data.sh DEST --repo PATH"; REPO="$2"; shift ;;
    --repo=*) REPO="${1#--repo=}" ;;
    -h|--help) usage; exit 0 ;;
    --) shift; while [ $# -gt 0 ]; do set_dest "$1"; shift; done; break ;;
    -*) refuse "Unknown option $1. Usage: ops/backup_data.sh DEST [--check] [--repo PATH] [--allow-cloud]. A destination whose name starts with a dash goes after --, as in: ops/backup_data.sh -- $1" ;;
    *) set_dest "$1" ;;
  esac
  shift
done
[ -n "$DEST" ] || { usage >&2; exit 2; }

# ---- the checkout ----------------------------------------------------------------------------------------------------
if [ -z "$REPO" ]; then
  REPO="$(cd "$(dirname "$0")/.." && pwd -P)"
else
  [ -d "$REPO" ] || refuse "The checkout $REPO does not exist."
  REPO="$(cd -- "$REPO" && pwd -P)"
fi
[ -d "$REPO/nfl-weather" ] && [ -d "$REPO/cfb-weather" ] ||
  refuse "$REPO does not look like the Value Finder checkout: it has no nfl-weather or cfb-weather folder."

# ---- the destination, and the rules that refuse it -------------------------------------------------------------------
[ -e "$DEST" ] || refuse "The destination $DEST does not exist. Plug in the backup drive, or connect to the other Mac's shared folder, and check the name."
[ -d "$DEST" ] || refuse "The destination $DEST is not a folder."
DEST_P="$(cd -- "$DEST" 2>/dev/null && pwd -P)" || refuse "The destination $DEST can't be opened."
case "$DEST" in /*) DEST_ABS="$DEST" ;; *) DEST_ABS="$PWD/$DEST" ;; esac
B="$DEST_P/value-finder-backup"

case "$DEST_P/" in
  "$REPO/"*) refuse "The destination $DEST is inside the checkout ($REPO). A backup has to be outside it, on another disk." ;;
esac

# The service a path looks synced by (nothing when none), judged by the path's name only.
cloud_service() {
  case "$(printf '%s/' "$1" | tr '[:upper:]' '[:lower:]')" in
    */library/mobile\ documents/*|*icloud*) echo "iCloud Drive" ;;
    *dropbox*) echo "Dropbox" ;;
    */library/cloudstorage/google*|*google\ drive*|*googledrive*) echo "Google Drive" ;;
    *onedrive*) echo "OneDrive" ;;
    */library/cloudstorage/*) echo "a cloud service" ;;
  esac
}
if [ "$ALLOW_CLOUD" -eq 0 ]; then
  svc="$(cloud_service "$DEST_ABS")"
  [ -n "$svc" ] || svc="$(cloud_service "$DEST_P")"
  [ -z "$svc" ] || refuse "The destination $DEST looks like a folder that $svc copies to the internet. Putting the paid data there is your explicit choice to make (its terms of use, and its size), so it is refused unless you add --allow-cloud."
fi

# ---- what it copies --------------------------------------------------------------------------------------------------
# The sharp-markets data folder, as settings.py finds it: MARKETS_DATA_DIR, else MARKETS_ROOT/data, else sharp-markets/data.
MDATA="${MARKETS_DATA_DIR:-${MARKETS_ROOT:-$REPO/sharp-markets}/data}"
case "$MDATA" in /*) ;; *) MDATA="$REPO/sharp-markets/$MDATA" ;; esac
FSTATE="${FOOTBALL_ACQUISITION_STATE_DIR:-$HOME/Library/Application Support/ValueFinder/football-acquisition-state}"
FEVID="${FOOTBALL_ACQUISITION_EVIDENCE_DIR:-$HOME/Library/Application Support/ValueFinder/football-acquisition-evidence}"
case "$FSTATE" in /*) ;; *) refuse "FOOTBALL_ACQUISITION_STATE_DIR must be an absolute folder path." ;; esac
case "$FEVID" in /*) ;; *) refuse "FOOTBALL_ACQUISITION_EVIDENCE_DIR must be an absolute folder path." ;; esac

# One entry per folder (or file): group, kind (dir or file), source, place in the backup.
N=0
add() { G[N]="$1"; K[N]="$2"; SRC[N]="$3"; REL[N]="$4"; N=$((N + 1)); }
add 1 dir "$MDATA/raw" "sharp-markets/data/raw"
# The complete parent includes per-root caches/receipts/ledgers AND central registrations/reservations.
add 1 dir "$FSTATE" "home-state/football-acquisition-state"
add 1 dir "$REPO/strategy-research/football_archive/acquisition" "strategy-research/football_archive/acquisition"
add 1 dir "$FEVID" "home-state/football-acquisition-evidence"
for p in nfl-weather cfb-weather; do
  seen=" "
  # Each oddsapi* folder on this Mac, and each one already in the backup, so that one gone missing here is reported.
  for d in "$REPO/$p/data/raw"/oddsapi* "$B/$p/data/raw"/oddsapi*; do
    [ -d "$d" ] || continue
    name="${d##*/}"
    case "$seen" in *" $name "*) continue ;; esac
    seen="$seen$name "
    add 1 dir "$REPO/$p/data/raw/$name" "$p/data/raw/$name"
  done
done
for p in nfl-weather cfb-weather; do add 2 dir "$REPO/$p/data/forward" "$p/data/forward"; done
add 3 dir "$HOME/.cache/value-finder" "home-cache/value-finder"
add 3 file "$MDATA/markets.duckdb" "sharp-markets/data/markets.duckdb"
# DuckDB's write-ahead file belongs with the markets.duckdb beside it. One the backup still has from an older
# markets.duckdb is moved into replaced/ once this Mac's markets.duckdb (which has none) is copied.
WALREL="sharp-markets/data/markets.duckdb.wal"
if [ -e "$MDATA/markets.duckdb.wal" ] || [ -e "$B/$WALREL" ] || [ -L "$B/$WALREL" ]; then
  add 3 file "$MDATA/markets.duckdb.wal" "$WALREL"
fi
LABEL[1]="Group 1, the paid data"
LABEL[2]="Group 2, the forward-test records"
LABEL[3]="Group 3, slow to re-create"

# ---- a copy on the same disk is not a backup --------------------------------------------------------------------------
# Compare the devices (stat), and the physical disk behind each (diskutil: the whole disk of the APFS physical store),
# which also catches a second volume made on this Mac's own disk. When the destination is a disk image, the same two
# tests apply to the image's file, and to that file's own disk image if it is on one. A network share has no /dev disk,
# so only its device is compared.
dev_of() { stat -L -f %d "$1" 2>/dev/null; }
node_of() { df -P "$1" 2>/dev/null | awk 'NR == 2 { print $1 }'; }
# One line of "diskutil info" for disk $1: the value after the name $2.
disk_info() {
  diskutil info "$1" 2>/dev/null |
    awk -v k="$2:" '{ sub(/^ +/, "") } index($0, k) == 1 { v = substr($0, length(k) + 1); sub(/^ +/, "", v); print v; exit }'
}
physical_disk_of() {
  local node store
  node="$(node_of "$1")"
  case "$node" in /dev/disk*) ;; *) return 0 ;; esac
  store="$(disk_info "$node" "APFS Physical Store")"
  if [ -n "$store" ]; then disk_info "$store" "Part of Whole"; else disk_info "$node" "Part of Whole"; fi
}
# The file of the disk image a path is on: nothing when it is not on a disk image, "?" when hdiutil doesn't say.
image_file_of() {
  local node f
  node="$(node_of "$1")"
  case "$node" in /dev/disk*) ;; *) return 0 ;; esac
  [ "$(disk_info "$node" Protocol)" = "Disk Image" ] || return 0
  f="$(hdiutil info 2>/dev/null | awk -v n="$node" '
    /^=+$/ { p = "" }
    /^image-path *:/ { p = $0; sub(/^image-path *: */, "", p) }
    $1 == n { print p; exit }')"
  printf '%s' "${f:-?}"
}
# Where the destination's data physically lives: the destination, then each disk image's file under it.
CP[0]="$DEST_P" CDEV[0]="$(dev_of "$DEST_P")" CPHYS[0]="$(physical_disk_of "$DEST_P")"
NC=1
while [ $NC -lt 6 ]; do
  img="$(image_file_of "${CP[$((NC - 1))]}")"
  [ -n "$img" ] || break
  [ "$img" != "?" ] || refuse "The destination $DEST is on a disk image, and hdiutil could not say where the image's file is, so the script can't tell whether it is on this Mac's own disk. Use an external drive or the other Mac's shared folder."
  CP[NC]="$img" CDEV[NC]="$(dev_of "$img")" CPHYS[NC]="$(physical_disk_of "$img")"
  NC=$((NC + 1))
done
DDEV="${CDEV[0]}"
i=0
while [ $i -lt $N ]; do
  s="${SRC[$i]}"
  if [ -e "$s" ]; then
    sdev="$(dev_of "$s")" sphys="$(physical_disk_of "$s")"
    c=0
    while [ $c -lt $NC ]; do
      what="The destination $DEST is"
      [ $c -eq 0 ] || what="The destination $DEST is a disk image whose file, ${CP[$c]}, is"
      [ "$sdev" != "${CDEV[$c]}" ] ||
        refuse "$what on the same disk as $s. A copy on the same disk is not a backup: if the disk fails, both are lost. Use an external drive or the other Mac's shared folder."
      [ -z "${CPHYS[$c]}" ] || [ "$sphys" != "${CPHYS[$c]}" ] ||
        refuse "$what on the same physical disk (${CPHYS[$c]}) as $s. A copy on the same disk is not a backup: if the disk fails, both are lost. Use an external drive or the other Mac's shared folder."
      c=$((c + 1))
    done
  fi
  i=$((i + 1))
done

# The backup folder, and every folder the copy writes into under it, must be a real folder on the drive: a link there
# would send the copy wherever it points.
if [ -e "$B" ] || [ -L "$B" ]; then
  [ ! -L "$B" ] || refuse "On the drive, $B is a link to somewhere else, so the copy would land there. The backup is written only into a real folder on the drive: rename that link, then run again."
  [ -d "$B" ] || refuse "On the drive, $B is not a folder."
  [ "$(dev_of "$B")" = "$DDEV" ] || refuse "On the drive, $B is another disk mounted there. Use a real folder on the drive."
fi
real_folders() {    # $1: a path under the backup folder; $2 "all" to check its last part too
  local rest="$1" path="$B" part
  while [ -n "$rest" ]; do
    part="${rest%%/*}"
    if [ "$part" = "$rest" ]; then rest=""; else rest="${rest#*/}"; fi
    path="$path/$part"
    [ -n "$rest" ] || [ "$2" = all ] || break
    [ ! -L "$path" ] || refuse "On the backup, $path is a link to somewhere else, so a copy into it would land there. The backup is written only into real folders on the drive: tell the hub."
  done
}
i=0
while [ $i -lt $N ]; do
  if [ "${K[$i]}" = dir ]; then real_folders "${REL[$i]}" all; else real_folders "${REL[$i]}" parent; fi
  i=$((i + 1))
done
real_folders forward-snapshots all
real_folders replaced all

if [ "$CHECK" -eq 0 ]; then
  [ -w "$DEST_P" ] || refuse "The destination $DEST can't be written to. If it is a drive, check that it isn't read-only (in Finder: Get Info, Sharing & Permissions)."
  [ ! -e "$B" ] || [ -w "$B" ] || refuse "The backup folder $B can't be written to."
fi

# ---- where this backup comes from -------------------------------------------------------------------------------------
# Two Macs or checkouts writing to one backup would replace each other's files. The backup records its source, and a
# run from another one is refused unless --new-source says the data has moved on purpose.
HOST_ID="$(ioreg -rd1 -c IOPlatformExpertDevice 2>/dev/null | awk -F'"' '/"IOPlatformUUID"/ { print $4; exit }')"
[ -n "$HOST_ID" ] || HOST_ID="unknown"
HOST_NAME="$(scutil --get ComputerName 2>/dev/null || hostname -s 2>/dev/null)"
SOURCE_TXT="$B/source.txt"
source_field() { sed -n "s/^$1: //p" "$SOURCE_TXT" 2>/dev/null | head -1; }
MOVED=""
if [ -f "$SOURCE_TXT" ]; then
  if [ "$(source_field machine)" != "$HOST_ID" ] || [ "$(source_field checkout)" != "$REPO" ] ||
     [ "$(source_field 'sharp-markets data folder')" != "$MDATA" ] ||
     { [ -n "$(source_field 'football state folder')" ] && [ "$(source_field 'football state folder')" != "$FSTATE" ]; } ||
     { [ -n "$(source_field 'football evidence folder')" ] && [ "$(source_field 'football evidence folder')" != "$FEVID" ]; }; then
    was_id="$(source_field machine)"
    MOVED="This backup was last made from $(source_field 'computer name') (Mac ${was_id%%-*}, checkout $(source_field checkout), sharp-markets data folder $(source_field 'sharp-markets data folder'), football state $(source_field 'football state folder'), football evidence $(source_field 'football evidence folder')). This run is from $HOST_NAME (Mac ${HOST_ID%%-*}, checkout $REPO, sharp-markets data folder $MDATA, football state $FSTATE, football evidence $FEVID)."
  fi
fi
if [ -n "$MOVED" ] && [ "$CHECK" -eq 0 ] && [ "$NEW_SOURCE" -eq 0 ]; then
  refuse "$MOVED A backup from here would replace that one's files with this Mac's. If the data now lives here for good (after the move to the Mac Studio, say), run the same command again with --new-source: every file it replaces is kept in value-finder-backup/replaced/. If not, use another drive or folder, or run it where the backup was made."
fi

# ---- helpers -----------------------------------------------------------------------------------------------------------
WORK="$(mktemp -d "${TMPDIR:-/tmp}/vf-backup.XXXXXX")" || { echo "Could not make a temporary folder." >&2; exit 2; }
trap 'rm -rf "$WORK"' EXIT
trap 'exit 130' INT TERM
START="$(date +%s)"
STAMP="$(date -u -r "$START" +%Y-%m-%dT%H%M%SZ)"
# For --check: when the last backup began, from its snapshot's name (finished or not). A file written on this Mac since
# then is new or changed since the last backup, which the next backup copies; it is listed, and it is not a FAIL.
LAST=0 LASTSHOW=""
if [ "$CHECK" -eq 1 ] && [ -d "$B/forward-snapshots" ]; then
  latest="$(ls -a "$B/forward-snapshots" |
    sed -n 's/^\(\.incomplete-\)\{0,1\}\([0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}T[0-9]\{6\}Z\).*/\2/p' | sort | tail -1)"
  if [ -n "$latest" ]; then
    LAST="$(date -j -u -f '%Y-%m-%dT%H%M%SZ' "$latest" +%s 2>/dev/null)" || LAST=0
    LASTSHOW="$(date -j -u -f '%Y-%m-%dT%H%M%SZ' "$latest" '+%Y-%m-%d %H:%M UTC' 2>/dev/null)"
  fi
fi
if [ -x /sbin/sha256sum ]; then SHA="/sbin/sha256sum"
elif command -v sha256sum >/dev/null 2>&1; then SHA="sha256sum"
else SHA="shasum -a 256"; fi

# Names never copied, and never opened. Keys are replaced, not backed up; the rest is re-created or half-written.
# Matched in upper or lower case: this Mac's disk ignores case, so .ENV is the same file programs open as .env.
KEYNAMES=('.env*' '*.env' env .netrc kaggle.json .kaggle '*.pem' '*.p12' '*.key' 'id_rsa*' 'id_ed25519*' '*secret*'
          '*credential*' '*password*' '*api_key*' '*api-key*' '*apikey*' '*token*.json' 'service-account*.json')
SKIPNAMES=("${KEYNAMES[@]}" .venv .git .DS_Store '._*' '*.tmp')
EXCL=() FIND_KEY=() FIND_SKIP=()
# rsync's patterns know no "ignore case", so each letter becomes a pair: .env* is .[Ee][Nn][Vv]*.
while IFS= read -r n; do EXCL+=("--exclude=$n"); done <<EOF
$(printf '%s\n' "${SKIPNAMES[@]}" | awk '{ o = ""; for (x = 1; x <= length($0); x++) { c = substr($0, x, 1)
  u = toupper(c); l = tolower(c); o = o (u != l ? "[" l u "]" : c) } print o }')
EOF
for n in "${SKIPNAMES[@]}"; do FIND_SKIP+=(-o -iname "$n"); done
for n in "${KEYNAMES[@]}"; do FIND_KEY+=(-o -iname "$n"); done
FIND_KEY=("${FIND_KEY[@]:1}")
FIND_SKIP=("${FIND_SKIP[@]:1}")
# A name with a line break in it can't be listed one per line; such names are listed on their own (odd_names).
FIND_EX=("${FIND_SKIP[@]}" -o -name "*$NL*")

add_num() { awk -v a="$1" -v b="$2" 'BEGIN { printf "%.0f", a + b }'; }
commas() { awk -v n="$1" 'BEGIN { s = sprintf("%.0f", n); o = ""
  while (length(s) > 3) { o = "," substr(s, length(s) - 2) o; s = substr(s, 1, length(s) - 3) } print s o }'; }
human() { awk -v b="$1" 'BEGIN { if (b >= 1e9) printf "%.1f GB\n", b / 1e9; else if (b >= 1e6) printf "%.1f MB\n", b / 1e6
  else if (b >= 1e3) printf "%.1f KB\n", b / 1e3; else printf "%d bytes\n", b }'; }
# "1 file", "3,921 files": count $1 of the thing named $2.
count() { if [ "$1" = 1 ]; then printf '1 %s' "$2"; else printf '%s %ss' "$(commas "$1")" "$2"; fi; }
# "54,351,210 bytes (54.4 MB)", or "88 bytes".
exact_bytes() {
  if awk -v b="$1" 'BEGIN { exit !(b >= 1000) }'; then printf '%s bytes (%s)' "$(commas "$1")" "$(human "$1")"
  else printf '%s bytes' "$1"; fi
}
shown() {
  local s="$1"
  case "$s" in "$REPO/"*) s="${s#"$REPO/"}" ;; "$HOME/"*) s="~/${s#"$HOME/"}" ;; esac
  printf '%s' "$s"
}
# Bytes free at a path. The field before the "NN%" one, so a name with spaces can't shift it.
free_bytes() {
  df -Pk "$1" 2>/dev/null | awk 'NR == 2 { for (x = 2; x <= NF; x++) if ($x ~ /^[0-9]+%$/) { printf "%.0f", $(x - 1) * 1024; exit } }'
}
kind_of() { if [ -L "$1" ]; then echo l; elif [ -f "$1" ]; then echo f; elif [ -d "$1" ]; then echo d; elif [ -e "$1" ]; then echo o; fi; }
kind_word() { case "$1" in f) echo file ;; d) echo folder ;; l) echo link ;; *) echo "special file" ;; esac; }

# Every entry under folder $1 (files, folders, links), written to $2, one line each:
#   type<TAB>size<TAB>mtime<TAB>link target<TAB>./path      (type: f file, d folder, l link, o anything else)
# never entering the names that are not copied. Returns non-zero, with find's and stat's messages in $2.err (one line
# each, naming the file), when part of the folder could not be read, or a name could not be looked at (a path longer
# than macOS allows, say).
list_entries() {
  local rc=0
  ( cd "$1" && find . -mindepth 1 \( "${FIND_EX[@]}" \) -prune -o -print0 ) > "$2.names" 2> "$2.err" || rc=1
  ( cd "$1" && xargs -0 stat -f '%Sp%t%z%t%m%t%Y%t%N' < "$2.names" 2>> "$2.err" ) |
    awk -F'\t' 'BEGIN { OFS = "\t" } { t = substr($1, 1, 1); $1 = (t == "-") ? "f" : (t == "d" || t == "l") ? t : "o"; print }' > "$2" || rc=1
  [ ! -s "$2.err" ] || rc=1
  return $rc
}
# Each line of $1.err (the messages of list_entries) as a FAIL line "1<TAB>could not be read <where> (why)<TAB>path",
# the path being $3 and, when the message names one ("stat: ./a/b: stat: File name too long", "find: ./a: Permission
# denied"), the file under it.
read_errors() {
  awk -v where="$2" -v under="$3" 'NF {
    path = ""; msg = $0
    if (match($0, /^[a-z]+: \.\//)) {
      rest = substr($0, RLENGTH + 1); k = 0
      for (x = 1; x < length(rest); x++) if (substr(rest, x, 2) == ": ") k = x
      if (k > 0) { path = "/" substr(rest, 1, k - 1); msg = substr(rest, k + 2); sub(/: l?stat$/, "", path) }
    }
    printf "1\tcould not be read %s (%s)\t%s%s\n", where, msg, under, path }' "$1.err"
}
# Names under folder $1 with a line break in them, one per line, the break shown as "?".
odd_names() { ( cd "$1" && find . -mindepth 1 \( "${FIND_SKIP[@]}" \) -prune -o -name "*$NL*" -prune -print0 ) 2>/dev/null | tr '\n\0' '?\n'; }
# Names under folder $1 that look like key files (never copied, never opened), one per line.
key_names() { ( cd "$1" && find . -mindepth 1 \( -iname .venv -o -iname .git \) -prune -o \( "${FIND_KEY[@]}" \) -prune -print ) 2>/dev/null; }
# The SHA-256 of each ./path listed in file $2 (one per line) under folder $1, as sha256sum prints them, into $3.
hash_list() { ( cd "$1" && tr '\n' '\0' < "$2" | xargs -0 $SHA ) > "$3" 2>/dev/null; }

# awk functions shared by the comparisons below.
AWKLIB='
function rest4(s,   k) { for (k = 0; k < 4; k++) s = substr(s, index(s, "\t") + 1); return s }
function unesc(s,   o, x, c, len) { o = ""; len = length(s)
  for (x = 1; x <= len; x++) { c = substr(s, x, 1); if (c == "\\" && x < len) { x++; c = substr(s, x, 1); if (c == "n") c = "\n" } o = o c }
  return o }
function hname(line) { return substr(line, 1, 1) == "\\" ? unesc(substr(line, 68)) : substr(line, 67) }
function hval(line) { return substr(line, 1, 1) == "\\" ? substr(line, 2, 64) : substr(line, 1, 64) }
function show(p) { sub(/^\.\//, "", p); return under "/" p }
function kind(t) { return t == "f" ? "file" : t == "d" ? "folder" : t == "l" ? "link" : "special file" }
function shrinks(p) { return group == 1 || p !~ /_state\.json$/ }
function blocks(n) { return (n + 0 <= 0) ? 4096 : int((n + 4095) / 4096) * 4096 }
# A partial copy that a stopped rsync left: ".NAME.XXXXXX" (6 letters and digits) or ".NAME.XXXXXXXXXX" (10, as the
# rsync of macOS makes them), where NAME is a file beside it on this Mac (st holds the entries of the source).
function leftover(p,   b, d, s) {
  b = p; sub(/.*\//, "", b); d = substr(p, 1, length(p) - length(b))
  if (substr(b, 1, 1) != ".") return 0
  s = b; sub(/.*\./, "", s)
  if ((length(s) != 6 && length(s) != 10) || s ~ /[^A-Za-z0-9]/) return 0
  b = substr(b, 2, length(b) - length(s) - 2)
  return b != "" && ((d b) in st) && st[d b] == "f"
}
function under_clash(p) { while (sub(/\/[^\/]*$/, "", p)) if (p in clash) return 1; return 0 }
'

# ---- what is on this Mac now ---------------------------------------------------------------------------------------------
GF[1]=0 GF[2]=0 GF[3]=0 GB[1]=0 GB[2]=0 GB[3]=0
i=0
while [ $i -lt $N ]; do
  nf=0 nb=0 LERR[i]=0
  if [ "${K[$i]}" = dir ] && [ -d "${SRC[$i]}" ]; then
    list_entries "${SRC[$i]}" "$WORK/$i.s" || LERR[i]=1
    read -r nf nb <<EOF
$(awk -F'\t' '$1 == "f" { n++; b += $2 } END { printf "%d %.0f\n", n, b }' "$WORK/$i.s")
EOF
    key_names "${SRC[$i]}" | while IFS= read -r k; do printf '%s/%s\n' "$(shown "${SRC[$i]}")" "${k#./}"; done >> "$WORK/keys"
  elif [ "${K[$i]}" = file ] && [ -f "${SRC[$i]}" ]; then
    nf=1 nb="$(stat -L -f %z "${SRC[$i]}")"
  fi
  F[i]=$nf Z[i]=$nb
  g=${G[$i]}
  GF[g]=$((GF[g] + nf))
  GB[g]="$(add_num "${GB[$g]}" "$nb")"
  i=$((i + 1))
done

if [ "$CHECK" -eq 1 ]; then
  echo "Checking the backup in $B against $REPO on $HOST_NAME (copying nothing)."
else
  echo "Backing up $REPO on $HOST_NAME to $B."
fi
[ -z "${MARKETS_DATA_DIR:-}${MARKETS_ROOT:-}" ] || echo "The sharp-markets data folder is $MDATA (set by MARKETS_DATA_DIR or MARKETS_ROOT)."
if [ -n "$MOVED" ] && [ "$CHECK" -eq 1 ]; then echo "Note: $MOVED"
elif [ -n "$MOVED" ]; then echo "Allowed by --new-source: $MOVED"; fi
echo
echo "On this Mac now:"
for g in 1 2 3; do
  printf '  %s: %s, %s\n' "${LABEL[$g]}" "$(count "${GF[$g]}" file)" "$(human "${GB[$g]}")"
  i=0
  while [ $i -lt $N ]; do
    if [ "${G[$i]}" = "$g" ]; then
      if [ -e "${SRC[$i]}" ]; then
        printf '      %-44s %15s %10s\n' "$(shown "${SRC[$i]}")" "$(count "${F[$i]}" file)" "$(human "${Z[$i]}")"
        [ "${LERR[$i]}" = 0 ] || echo "        (part of it could not be read, so these numbers are short: see the FAIL lines below)"
      elif [ "$g" != 3 ] && { [ -e "$B/${REL[$i]}" ] || [ -L "$B/${REL[$i]}" ]; }; then
        printf '      %-44s not on this Mac, but the backup has it\n' "$(shown "${SRC[$i]}")"
      elif [ "$g" != 3 ]; then
        printf '      %-44s not created yet; nothing to copy\n' "$(shown "${SRC[$i]}")"
      else
        printf '      %-44s not on this Mac (nothing to copy)\n' "$(shown "${SRC[$i]}")"
      fi
    fi
    i=$((i + 1))
  done
done
if [ -s "$WORK/keys" ]; then
  echo "  Left out, because each name looks like a key file (keys are replaced, never backed up, and never opened):"
  sed 's/^/      /' "$WORK/keys"
fi

# ---- before copying: what the backup already holds ------------------------------------------------------------------------
# For each name on the backup: a file or folder that is something else here, and (groups 1 and 2) a file that got smaller
# here, are not copied: their rsync exclusions go to $WORK/$i.pat (group 3's problems to $WORK/$i.hold). With
# --accept-changes they are instead moved into replaced/ first, as are the files of groups 1 and 2 gone from this Mac:
# their paths go to $WORK/$i.moves.
HOLD_AWK="$AWKLIB"'
function hold(p,   q) {
  q = p; sub(/^\.\//, "", q)
  if (q ~ /\\/) print "!whole" > pats; else { gsub(/[*?[]/, "\\\\&", q); print "/" q > pats }
}
function aside(p,   q) { clash[p] = 1; q = p; sub(/^\.\//, "", q); print q > moves }
FILENAME == ARGV[1] { p = rest4($0); st[p] = $1; ss[p] = $2; next }
{ p = rest4($0) }
under_clash(p) { next }
!(p in st) { if (accept && group != 3 && $1 == "f") aside(p); next }
($1 == "f" || $1 == "d") && $1 != st[p] {
  if (accept) aside(p)
  else { hold(p); printf "1\t%s\t%s\n", "is a " kind(st[p]) " on this Mac but a " kind($1) " on the backup; not copied, so the backup keeps its " kind($1), show(p) }
  next }
group != 3 && $1 == "f" && st[p] == "f" && $2 + 0 > ss[p] + 0 && shrinks(p) && !accept { hold(p) }'
NEEDED=0
i=0
while [ $i -lt $N ]; do
  s="${SRC[$i]}" d="$B/${REL[$i]}" g="${G[$i]}" n=0
  : > "$WORK/$i.pat"
  : > "$WORK/$i.hold"
  : > "$WORK/$i.moves"
  if [ "${K[$i]}" = dir ] && [ -d "$s" ]; then
    if [ -d "$d" ]; then
      list_entries "$d" "$WORK/$i.d"
      [ "$CHECK" -eq 1 ] ||
        awk -F'\t' -v pats="$WORK/$i.pat" -v moves="$WORK/$i.moves" -v group="$g" -v accept="$ACCEPT" \
          -v under="${REL[$i]}" "$HOLD_AWK" "$WORK/$i.s" "$WORK/$i.d" > "$WORK/$i.hold"
    else
      : > "$WORK/$i.d"
    fi
    # Space: every file that is new, or whose size or time differs from the copy's (as rsync decides), rounded up to
    # whole 4 KB blocks; the snapshot copies all of group 2 again.
    n="$(awk -F'\t' -v snap="$([ "$g" = 2 ] && echo 1 || echo 0)" "$AWKLIB"'
      FILENAME == ARGV[1] { if ($1 == "f") have[rest4($0)] = $2 "\t" $3; next }
      $1 == "f" { p = rest4($0); if (!(p in have) || have[p] != $2 "\t" $3) b += blocks($2); if (snap) b += blocks($2) }
      END { printf "%.0f", b }' "$WORK/$i.d" "$WORK/$i.s")"
  elif [ "${K[$i]}" = file ] && [ -e "$s" ]; then
    sk="$(kind_of "$s")" dk="$(kind_of "$d")"
    if { [ "$dk" = f ] || [ "$dk" = d ]; } && [ "$sk" != "$dk" ] && [ "$ACCEPT" -eq 1 ]; then
      echo "." > "$WORK/$i.moves"
    elif { [ "$dk" = f ] || [ "$dk" = d ]; } && [ "$sk" != "$dk" ]; then
      printf '1\t%s\t%s\n' "is a $(kind_word "$sk") on this Mac but a $(kind_word "$dk") on the backup; not copied, so the backup keeps its $(kind_word "$dk")" "${REL[$i]}" > "$WORK/$i.hold"
      echo "!whole" > "$WORK/$i.pat"
    elif [ "$dk" != f ] || [ "$(stat -L -f '%z %m' "$s")" != "$(stat -f '%z %m' "$d")" ]; then
      n="$(awk -v z="$(stat -L -f %z "$s")" "$AWKLIB"'BEGIN { printf "%.0f", blocks(z) }')"
    fi
  fi
  tr '\n' '\0' < "$WORK/$i.pat" > "$WORK/$i.pat0"
  NEEDED="$(add_num "$NEEDED" "$n")"
  i=$((i + 1))
done
WANT="$(awk -v a="$NEEDED" 'BEGIN { printf "%.0f", a + a / 100 + 10e6 }')"      # plus a little room for folders
FREE="$(free_bytes "$DEST_P")"
echo
echo "A backup now writes about $(human "$NEEDED") (new or changed files, and the snapshot of group 2). $DEST has $(human "${FREE:-0}") free."
if [ "$CHECK" -eq 0 ] && [ -n "$FREE" ] && awk -v f="$FREE" -v w="$WANT" 'BEGIN { exit !(f < w) }'; then
  refuse "The destination $DEST has $(human "$FREE") free, and this backup needs about $(human "$WANT"), with a little room to spare. Free up space there, or use a bigger drive."
fi

# ---- copy ------------------------------------------------------------------------------------------------------------
CF[1]="" CF[2]="" CF[3]=""
SNAPNAME="" SNAPTMP="" REPLACED=0 REPNAME=""
# Move $1, on the backup, to $2 in this run's replaced/ folder. Never over anything already there: returns non-zero
# instead.
set_aside() {
  if [ -e "$2" ] || [ -L "$2" ]; then echo "  Not moved, because $2 already exists: $1" >&2; return 1; fi
  mkdir -p "$(dirname "$2")" && mv "$1" "$2"
}
if [ "$CHECK" -eq 0 ]; then
  mkdir -p "$B/forward-snapshots" "$B/replaced" || refuse "Could not make the folder $B."
  # This run's replaced/ folder: one that no earlier run used, even when the clock gives the same second twice. mkdir
  # makes it or fails, in one step, so two runs can't both take it.
  REPNAME="$STAMP"
  k=2
  until mkdir "$B/replaced/$REPNAME" 2>/dev/null; do
    [ -e "$B/replaced/$REPNAME" ] || [ -L "$B/replaced/$REPNAME" ] || refuse "Could not make the folder $B/replaced/$REPNAME."
    REPNAME="$STAMP-$k"; k=$((k + 1))
  done
  REP="$B/replaced/$REPNAME"
  echo
  echo "Copying (nothing on the backup is deleted; a file the copy replaces is kept in value-finder-backup/replaced/$REPNAME/):"
  { printf 'machine: %s\n' "$HOST_ID"; printf 'computer name: %s\n' "$HOST_NAME"; printf 'checkout: %s\n' "$REPO"
    printf 'sharp-markets data folder: %s\n' "$MDATA"
    printf 'football state folder: %s\n' "$FSTATE"; printf 'football evidence folder: %s\n' "$FEVID"
    printf 'recorded: %s\n' "$STAMP"; } > "$SOURCE_TXT" ||
    refuse "Could not write $SOURCE_TXT."
  SNAPNAME="$STAMP"
  k=2
  while [ -e "$B/forward-snapshots/$SNAPNAME" ] || [ -e "$B/forward-snapshots/.incomplete-$SNAPNAME" ]; do
    SNAPNAME="$STAMP-$k"; k=$((k + 1))
  done
  SNAPTMP="forward-snapshots/.incomplete-$SNAPNAME"
  DUCKDONE=0
  i=0
  while [ $i -lt $N ]; do
    s="${SRC[$i]}" d="$B/${REL[$i]}" g="${G[$i]}" rc=0
    [ "$g" != 3 ] || [ ! -s "$WORK/$i.hold" ] || CF[3]="${CF[3]}$(cat "$WORK/$i.hold")"$'\n'
    if [ -e "$s" ]; then
      echo "  $(shown "$s")"
      # --accept-changes: the backup's copies that this Mac's files replace are moved aside first, never deleted.
      while IFS= read -r m; do
        if [ "$m" = . ]; then from="$d" to="$REP/${REL[$i]}" what="${REL[$i]}"
        else from="$d/$m" to="$REP/${REL[$i]}/$m" what="${REL[$i]}/$m"; fi
        set_aside "$from" "$to" ||
          CF[g]="${CF[$g]}$(printf '1\t%s\t%s' "could not be moved into replaced/ (its message is above), so it was left as it was" "$what")"$'\n'
      done < "$WORK/$i.moves"
      if grep -qx '!whole' "$WORK/$i.pat"; then
        [ "${K[$i]}" = file ] ||
          CF[g]="${CF[$g]}$(printf '1\t%s\t%s' "nothing of it was copied this time: a name that needs a decision has a backslash in it" "${REL[$i]}")"$'\n'
      elif [ "${K[$i]}" = dir ]; then
        # Archive mode keeps times and copies links as links. There is no --delete of any kind, and a file the copy
        # replaces is kept in replaced/ (-b).
        args=(-a "${EXCL[@]}" -b "--backup-dir=$REP/${REL[$i]}")
        [ ! -s "$WORK/$i.pat0" ] || args+=(--from0 "--exclude-from=$WORK/$i.pat0")
        mkdir -p "$d" && rsync "${args[@]}" "$s/" "$d/" || rc=$?
        if [ "$g" = 2 ]; then
          snaprc=0
          mkdir -p "$B/$SNAPTMP/${REL[$i]}" && rsync -a "${EXCL[@]}" "$s/" "$B/$SNAPTMP/${REL[$i]}/" || snaprc=$?
          [ $snaprc -eq 0 ] ||
            CF[g]="${CF[$g]}$(printf '1\t%s\t%s' "the copy into the new snapshot stopped with an error (code $snaprc; its message is above)" "$SNAPTMP/${REL[$i]}")"$'\n'
        fi
      else
        # One file, copied into its folder on the backup: rsync then replaces whatever has its name there (a link
        # too) and never follows a link out of the backup. The file it replaces is kept in replaced/ (-b).
        pdir="$(dirname "${REL[$i]}")"
        mkdir -p "$B/$pdir" && rsync -a -b "--backup-dir=$REP/$pdir" "$s" "$B/$pdir/" || rc=$?
        [ $rc -ne 0 ] || [ "${REL[$i]}" != sharp-markets/data/markets.duckdb ] || DUCKDONE=1
      fi
      if [ $rc -ne 0 ]; then
        CF[g]="${CF[$g]}$(printf '1\t%s\t%s' "the copy stopped with an error (code $rc; its message is above)" "${REL[$i]}")"$'\n'
      fi
    elif { [ -e "$d" ] || [ -L "$d" ]; } &&
         { { [ "$ACCEPT" -eq 1 ] && [ "$g" != 3 ]; } || { [ "${REL[$i]}" = "$WALREL" ] && [ "$DUCKDONE" -eq 1 ]; }; }; then
      # A folder of groups 1 and 2 gone from this Mac, with --accept-changes; or a markets.duckdb.wal on the backup
      # that belongs to the older markets.duckdb just replaced. Moved into replaced/, never deleted.
      if set_aside "$d" "$REP/${REL[$i]}"; then
        echo "  $(shown "$s"): not on this Mac, so the backup's copy was moved into value-finder-backup/replaced/$REPNAME/"
      else
        CF[g]="${CF[$g]}$(printf '1\t%s\t%s' "could not be moved into replaced/ (its message is above), so it was left as it was" "${REL[$i]}")"$'\n'
      fi
    fi
    i=$((i + 1))
  done
  REPLACED="$(find "$REP" ! -type d ! -name '._*' 2>/dev/null | awk 'END { print NR }')"
  if [ "$REPLACED" -eq 0 ]; then
    rmdir "$REP" 2>/dev/null; rmdir "$B/replaced" 2>/dev/null       # only when empty: nothing was kept this time
  else
    were=were; [ "$REPLACED" -ne 1 ] || were=was
    echo "  $(count "$REPLACED" file) on the backup $were replaced or set aside; the backup's older copies are kept in value-finder-backup/replaced/$REPNAME/."
  fi
fi

# ---- compare ---------------------------------------------------------------------------------------------------------
# Inputs, in this order: the source's and the copy's entry lists (list_entries), and the SHA-256 lists of the files on
# both (a shasum line that starts with a backslash has an escaped name). Prints "1<TAB>what<TAB>path" per problem,
# "new<TAB>what<TAB>path" for a file written on this Mac since the last backup began (--check only: last > 0), and
# "note<TAB>what<TAB>path" for a partial copy a stopped backup left.
COMPARE_AWK="$AWKLIB"'
FILENAME == ARGV[1] { p = rest4($0); st[p] = $1; ss[p] = $2; sm[p] = $3; sl[p] = $4; so[++ns] = p; next }
FILENAME == ARGV[2] { p = rest4($0); dt[p] = $1; ds[p] = $2; dl[p] = $4; dord[++nd] = p; next }
FILENAME == ARGV[3] { sh[hname($0)] = hval($0); next }
FILENAME == ARGV[4] { dh[hname($0)] = hval($0); next }
END {
  for (x = 1; x <= ns; x++) {
    p = so[x]; t = st[p]; why = ""
    if (under_clash(p)) continue
    if (p in dt) {
      if (dt[p] != t && dt[p] != "l") {
        clash[p] = 1
        printf "1\t%s\t%s\n", "is a " kind(t) " on this Mac but a " kind(dt[p]) " on the backup; the backup keeps its " kind(dt[p]) " and this name is not copied until the hub decides" (t == "l" ? " (a backup never follows a link, so what it points to is not backed up)" : ""), show(p)
        continue
      }
      if (dt[p] != t) why = "is a " kind(t) " on this Mac but a link on the backup"
      else if (t == "f") {
        if (ds[p] + 0 > ss[p] + 0 && shrinks(p) && !accept) {
          printf "1\t%s\t%s\n", "is smaller on this Mac (" ss[p] " bytes) than on the backup (" ds[p] " bytes); the backup keeps the larger copy until the hub decides", show(p)
          continue
        }
        if (ds[p] != ss[p]) why = "differs (size)"
        else if (!(p in sh)) why = "could not be read on this Mac"
        else if (!(p in dh)) why = "could not be read on the backup"
        else if (dh[p] != sh[p]) why = "differs (content)"
      } else if (t == "l" && dl[p] != sl[p]) why = "link differs"
    } else if (t == "f") why = "missing on the backup"
    else if (t == "l") why = "link missing on the backup"
    if (why == "") continue
    if (last + 0 > 0 && sm[p] + 0 >= last + 0) { printf "new\t%s\t%s\n", "new or changed since the last backup", show(p); continue }
    if (sm[p] + 0 >= start + 0) why = why ", changed on this Mac while this ran"
    printf "1\t%s\t%s\n", why, show(p)
  }
  for (x = 1; x <= nd; x++) {
    p = dord[x]
    if ((p in st) || dt[p] != "f" || under_clash(p)) continue
    if (leftover(p)) printf "note\t%s\t%s\n", "a partial copy that a stopped backup left (harmless: restores skip it)", show(p)
    else printf "1\t%s\t%s\n", "is on the backup but no longer on this Mac (the backup keeps it)", show(p)
  }
}'
# Compare source folder $1 with its copy $2, both ways, appending problems to $3 with paths shown under $4; $5 is the
# group, and $6 the "last backup" time (0 for none). Sets VF, VB and VL: the source's files, bytes and links.
VN=0
verify_dir() {
  local src="$1" dst="$2" out="$3" under="$4" group="$5" last="$6" w
  w="$WORK/v$VN"; VN=$((VN + 1))
  VF=0 VB=0 VL=0
  list_entries "$src" "$w.s" || read_errors "$w.s" "on this Mac" "$under" >> "$out"
  odd_names "$src" | while IFS= read -r o; do
    printf '1\t%s\t%s\n' "has a line break in its name, which this script can't check (rename it; the hub can help)" "$under/${o#./}"
  done >> "$out"
  read -r VF VB VL <<EOF
$(awk -F'\t' '$1 == "f" { n++; b += $2 } $1 == "l" { l++ } END { printf "%d %.0f %d\n", n, b, l }' "$w.s")
EOF
  if [ ! -d "$dst" ]; then
    [ "$VF" -eq 0 ] && [ "$VL" -eq 0 ] ||
      printf '%s\t%s\t%s\n' "$((VF + VL))" "no copy on the backup yet ($(count "$VF" file))" "$under" >> "$out"
    return 0
  fi
  list_entries "$dst" "$w.d" || read_errors "$w.d" "on the backup" "$under" >> "$out"
  awk -F'\t' "$AWKLIB"'FILENAME == ARGV[1] { if ($1 == "f") f[rest4($0)] = 1; next } $1 == "f" && (rest4($0) in f) { print rest4($0) }' \
    "$w.s" "$w.d" > "$w.both"
  hash_list "$src" "$w.both" "$w.sh"
  hash_list "$dst" "$w.both" "$w.dh"
  awk -F'\t' -v start="$START" -v last="$last" -v under="$under" -v group="$group" -v accept=0 "$COMPARE_AWK" \
      "$w.s" "$w.d" "$w.sh" "$w.dh" >> "$out"
}

# Make the new snapshot's list of its files' SHA-256 and give it its real name. Returns non-zero when it could not.
finish_snapshot() {
  local dir="$B/$SNAPTMP"
  list_entries "$dir" "$WORK/snap.s" || return 1
  awk -F'\t' "$AWKLIB"'$1 == "f" { p = rest4($0); if (p != "./checksums.txt") print p }' "$WORK/snap.s" > "$WORK/snap.f"
  hash_list "$dir" "$WORK/snap.f" "$WORK/snap.h"
  [ "$(awk 'END { print NR }' "$WORK/snap.f")" = "$(awk 'END { print NR }' "$WORK/snap.h")" ] || return 1
  # mv onto a folder that exists would put this one inside it, so a name taken since this run picked it is refused.
  [ ! -e "$B/forward-snapshots/$SNAPNAME" ] && [ ! -L "$B/forward-snapshots/$SNAPNAME" ] || return 1
  cp "$WORK/snap.h" "$dir/checksums.txt" && mv "$dir" "$B/forward-snapshots/$SNAPNAME"
}

# --check: every finished snapshot against the SHA-256 list saved in it, both ways.
SNAPS=0 SNAPFILES=0 SNAPINC=0
check_snapshots() {
  local dir="$B/forward-snapshots" name s out="$1" nf
  [ -d "$dir" ] || return 0
  ls -a "$dir" > "$WORK/snapnames"
  while IFS= read -r name; do
    case "$name" in .|..) continue ;; .incomplete-*) SNAPINC=$((SNAPINC + 1)); continue ;; .*) continue ;; esac
    s="$dir/$name"
    SNAPS=$((SNAPS + 1))
    if [ -L "$s" ] || [ ! -d "$s" ]; then
      printf '1\t%s\t%s\n' "is not a snapshot folder" "forward-snapshots/$name" >> "$out"; continue
    fi
    if [ ! -f "$s/checksums.txt" ]; then
      printf '1\t%s\t%s\n' "has no list of its files (checksums.txt), so it may be incomplete: never restore from it" "forward-snapshots/$name" >> "$out"
      continue
    fi
    list_entries "$s" "$WORK/sc.s" ||
      printf '1\t%s\t%s\n' "part of it could not be read ($(head -1 "$WORK/sc.s.err"))" "forward-snapshots/$name" >> "$out"
    awk -F'\t' "$AWKLIB"'$1 == "f" { p = rest4($0); if (p != "./checksums.txt") print p }' "$WORK/sc.s" > "$WORK/sc.f"
    hash_list "$s" "$WORK/sc.f" "$WORK/sc.h"
    nf="$(awk 'END { print NR }' "$WORK/sc.f")"
    SNAPFILES=$((SNAPFILES + nf))
    awk -v under="forward-snapshots/$name" "$AWKLIB"'
      FILENAME == ARGV[1] { p = hname($0); want[p] = hval($0); order[++n] = p; next }
      FILENAME == ARGV[2] { got[hname($0)] = hval($0); next }
      { present[$0] = 1; porder[++m] = $0 }
      END {
        for (x = 1; x <= n; x++) { p = order[x]
          if (!(p in present)) printf "1\t%s\t%s\n", "is in the snapshot'\''s list but missing from it", show(p)
          else if (!(p in got)) printf "1\t%s\t%s\n", "could not be read", show(p)
          else if (got[p] != want[p]) printf "1\t%s\t%s\n", "differs from the SHA-256 saved in the snapshot'\''s list", show(p)
        }
        for (x = 1; x <= m; x++) if (!(porder[x] in want)) printf "1\t%s\t%s\n", "is in the snapshot but not in its list", show(porder[x])
      }' "$s/checksums.txt" "$WORK/sc.h" "$WORK/sc.f" >> "$out"
  done < "$WORK/snapnames"
}

# Print one group's result: $1 label, $2 problems file, $3 what was compared ("7 files and 2 links, 88 bytes"), $4 what
# matched ("each has the same size and SHA-256 on the backup").
report() {
  local label="$1" pf="$2" what="$3" matched="$4" nnew nprob
  awk -F'\t' '$1 == "new"' "$pf" > "$pf.new"
  awk -F'\t' '$1 == "note"' "$pf" > "$pf.note"
  awk -F'\t' '$1 != "new" && $1 != "note"' "$pf" > "$pf.bad"
  nnew="$(awk 'END { print NR }' "$pf.new")"
  NEWER=$((NEWER + nnew))
  if [ ! -s "$pf.bad" ]; then
    if [ "$nnew" -eq 0 ]; then
      echo "OK    $label: $what; $matched."
    else
      echo "OK    $label: $what; $matched, except" \
           "$(count "$nnew" file) new or changed on this Mac since the last backup ($LASTSHOW), which the next backup copies:"
    fi
  else
    FAILED=1
    nprob="$(awk -F'\t' '{ s += $1 } END { print s + 0 }' "$pf.bad")"
    echo "FAIL  $label ($what): $(commas "$nprob") missing or different:"
    [ "$nnew" -eq 0 ] || echo "        (and $(count "$nnew" file) new or changed since the last backup, $LASTSHOW, listed after these)"
  fi
  cat "$pf.bad" "$pf.new" "$pf.note" |
    awk -F'\t' 'NR <= 20 { printf "        %s: %s\n", $3, $2 } END { if (NR > 20) printf "        ... and %d more lines like these\n", NR - 20 }'
}

echo
echo "Comparing every file of groups 1 and 2 on this Mac and on the backup, both ways, by size and SHA-256:"
if [ "$CHECK" -eq 1 ] && [ ! -d "$B" ]; then echo "  (There is no backup in $DEST yet: no value-finder-backup folder.)"; fi
FAILED=0 NEWER=0 SNAPDONE=""
LASTARG=0; [ "$CHECK" -eq 0 ] || LASTARG="$LAST"
for g in 1 2; do
  pf="$WORK/problems$g"
  printf '%s' "${CF[$g]}" > "$pf"
  files=0 bytes=0 links=0
  i=0
  while [ $i -lt $N ]; do
    if [ "${G[$i]}" = "$g" ]; then
      if [ ! -d "${SRC[$i]}" ]; then
        if [ -e "$B/${REL[$i]}" ] || [ -L "$B/${REL[$i]}" ]; then
          printf '1\t%s\t%s\n' "not on this Mac, but the backup has it (see \"If a line says FAIL\" in ops/BACKUP.md)" "$(shown "${SRC[$i]}")" >> "$pf"
        fi
      else
        verify_dir "${SRC[$i]}" "$B/${REL[$i]}" "$pf" "${REL[$i]}" "$g" "$LASTARG"
        files=$((files + VF)) links=$((links + VL))
        bytes="$(add_num "$bytes" "$VB")"
      fi
    fi
    i=$((i + 1))
  done
  where="on the backup"
  if [ "$g" = 2 ] && [ -n "$SNAPTMP" ] && [ -d "$B/$SNAPTMP" ]; then
    # The new snapshot, against this Mac. It keeps its .incomplete- name unless it matches.
    : > "$WORK/snapproblems"
    i=0
    while [ $i -lt $N ]; do
      if [ "${G[$i]}" = 2 ] && [ -d "${SRC[$i]}" ]; then
        verify_dir "${SRC[$i]}" "$B/$SNAPTMP/${REL[$i]}" "$WORK/snapproblems" "$SNAPTMP/${REL[$i]}" 2 0
      fi
      i=$((i + 1))
    done
    if [ ! -s "$WORK/snapproblems" ] && finish_snapshot; then
      SNAPDONE="forward-snapshots/$SNAPNAME"
      where="on the backup and in the snapshot $SNAPDONE"
    else
      cat "$WORK/snapproblems" >> "$pf"
      [ -s "$WORK/snapproblems" ] ||
        printf '1\t%s\t%s\n' "the snapshot's list of files could not be written, so it keeps its .incomplete- name" "$SNAPTMP" >> "$pf"
    fi
  fi
  what="$(count "$files" file)"
  [ "$links" -eq 0 ] || what="$what and $(count "$links" link)"
  report "${LABEL[$g]}" "$pf" "$what, $(exact_bytes "$bytes")" "each has the same size and SHA-256 $where"
done
if [ "$CHECK" -eq 1 ]; then
  echo "--    ${LABEL[3]}: $(count "${GF[3]}" file), $(human "${GB[3]}") on this Mac; --check does not compare it."
  : > "$WORK/snapcheck"
  check_snapshots "$WORK/snapcheck"
  if [ "$SNAPS" -gt 0 ] || [ -s "$WORK/snapcheck" ]; then
    report "Snapshots of the forward-test records" "$WORK/snapcheck" \
      "$(count "$SNAPS" snapshot), $(count "$SNAPFILES" file)" "each file has the SHA-256 saved in its snapshot's list"
  fi
  [ "$SNAPINC" -eq 0 ] ||
    echo "      ($(count "$SNAPINC" "more snapshot") in forward-snapshots, named .incomplete-..., did not finish or did not match: never restore from those.)"
elif [ -n "${CF[3]}" ]; then
  FAILED=1
  echo "FAIL  ${LABEL[3]}: the copy did not finish, or left something alone:"
  printf '%s' "${CF[3]}" | awk -F'\t' 'NF >= 3 { printf "        %s: %s\n", $3, $2 }'
else
  echo "--    ${LABEL[3]}: $(count "${GF[3]}" file), $(human "${GB[3]}") copied; not compared file by file (it can be re-created, slowly)."
fi

echo
if [ "$CHECK" -eq 1 ]; then
  if [ $FAILED -ne 0 ]; then echo "Check found problems: read the FAIL lines above (ops/BACKUP.md, \"If a line says FAIL\")."
  elif [ $NEWER -ne 0 ]; then echo "Check finished: groups 1 and 2 and the snapshots match on the backup, apart from what was written on this Mac since the last backup (listed above)."
  else echo "Check finished: groups 1 and 2 and the snapshots match on the backup."; fi
else
  result=OK; [ $FAILED -eq 0 ] || result=FAIL
  snapnote="snapshot $SNAPDONE verified"
  if [ -z "$SNAPDONE" ] && [ -d "$B/$SNAPTMP" ]; then snapnote="snapshot left as $SNAPTMP, not verified"
  elif [ -z "$SNAPDONE" ]; then snapnote="no records yet, so no snapshot"; fi
  printf '%s  %-4s  from %s (%s):%s  group 1: %s, %s; group 2: %s, %s (%s); group 3: %s, %s; %s kept in replaced/%s\n' \
    "$STAMP" "$result" "$HOST_NAME" "$HOST_ID" "$REPO" "$(count "${GF[1]}" file)" "$(human "${GB[1]}")" \
    "$(count "${GF[2]}" file)" "$(human "${GB[2]}")" "$snapnote" "$(count "${GF[3]}" file)" "$(human "${GB[3]}")" \
    "$(count "$REPLACED" file)" "$REPNAME" >> "$B/backup-log.txt" 2>/dev/null || true
  if [ $FAILED -eq 0 ] && [ -n "$SNAPDONE" ]; then
    echo "Backup finished: groups 1 and 2 match file for file. The forward-test records were also saved as $SNAPDONE."
  elif [ $FAILED -eq 0 ]; then
    echo "Backup finished: groups 1 and 2 match file for file. There are no forward-test records yet, so no snapshot."
  else
    echo "Backup finished with problems: read the FAIL lines above (ops/BACKUP.md, \"If a line says FAIL\")."
  fi
fi
exit $FAILED
