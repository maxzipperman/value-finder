#!/bin/bash
# Back up the paid odds data and the forward-test records to another disk. The owner's page: ops/BACKUP.md.
#
#   ops/backup_data.sh DEST                 copy into DEST/value-finder-backup/, then compare every file of groups 1 and 2
#   ops/backup_data.sh DEST --check         compare only: copy nothing and write nothing
#   ops/backup_data.sh DEST --repo PATH     back up that checkout (default: the one this script is in)
#   ops/backup_data.sh DEST --allow-cloud   allow a folder that iCloud Drive, Dropbox, Google Drive or OneDrive syncs
#
# What it copies, most important first:
#   group 1, the paid data: the sharp-markets data folder's raw/ (the folder MARKETS_DATA_DIR names when it is set, as
#            sharp-markets/src/markets/settings.py reads it) and each weather project's data/raw/oddsapi* folders
#   group 2, the forward-test records: each weather project's data/forward/, also kept at every run as a dated
#            snapshot in DEST/value-finder-backup/forward-snapshots/<UTC date and time>/
#   group 3, slow to re-create: ~/.cache/value-finder (the forecast archive) and sharp-markets' markets.duckdb
# Never copied: any .env or .env.* file, ~/.kaggle, a .venv or .git folder, Finder's .DS_Store files. Links are
# copied as links and never followed. The source is only read. On the destination, files are added or replaced
# (a file that changed since the last backup is copied again under its name) and never deleted.
# After copying, every file of groups 1 and 2 is compared on both sides by size and SHA-256. --check makes the same
# comparison, except that a file written on this Mac since the last backup began is listed as new or changed, not a FAIL.
# Exit status: 0 when groups 1 and 2 match, 1 on any FAIL, 2 when it refuses to start.
# Plain bash 3.2 and the tools macOS ships (rsync, find, stat, df, diskutil, sha256sum or shasum).
set -u
set -o pipefail
export LC_ALL=C

usage() { sed -n '4,7p' "$0" | sed 's/^# *//'; }

refuse() {
  printf '%s\n' "$1" >&2
  printf '%s\n' "Stopped before copying anything. ops/BACKUP.md explains each rule." >&2
  exit 2
}

DEST="" CHECK=0 ALLOW_CLOUD=0 REPO=""
while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECK=1 ;;
    --allow-cloud) ALLOW_CLOUD=1 ;;
    --repo) [ $# -ge 2 ] || refuse "--repo needs a folder: ops/backup_data.sh DEST --repo PATH"; REPO="$2"; shift ;;
    --repo=*) REPO="${1#--repo=}" ;;
    -h|--help) usage; exit 0 ;;
    -*) refuse "Unknown option $1. Usage: ops/backup_data.sh DEST [--check] [--repo PATH] [--allow-cloud]" ;;
    *) [ -z "$DEST" ] || refuse "Give one destination, not two ($DEST and $1). Put quotes around a name with spaces."
       DEST="$1" ;;
  esac
  shift
done
[ -n "$DEST" ] || { usage >&2; exit 2; }

# ---- the checkout --------------------------------------------------------------------------------------------------
if [ -z "$REPO" ]; then
  REPO="$(cd "$(dirname "$0")/.." && pwd -P)"
else
  [ -d "$REPO" ] || refuse "The checkout $REPO does not exist."
  REPO="$(cd "$REPO" && pwd -P)"
fi
[ -d "$REPO/nfl-weather" ] && [ -d "$REPO/cfb-weather" ] ||
  refuse "$REPO does not look like the Value Finder checkout: it has no nfl-weather or cfb-weather folder."

# ---- the destination, and the rules that refuse it -----------------------------------------------------------------
[ -e "$DEST" ] || refuse "The destination $DEST does not exist. Plug in the backup drive, or connect to the Mac Studio's shared folder, and check the name."
[ -d "$DEST" ] || refuse "The destination $DEST is not a folder."
DEST_P="$(cd "$DEST" 2>/dev/null && pwd -P)" || refuse "The destination $DEST can't be opened."
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

# One entry per folder (or file): group, kind (dir or file), whether it must be there, source, place in the backup.
N=0
add() { G[N]="$1"; K[N]="$2"; NEED[N]="$3"; SRC[N]="$4"; REL[N]="$5"; N=$((N + 1)); }
add 1 dir yes "$MDATA/raw" "sharp-markets/data/raw"
for p in nfl-weather cfb-weather; do
  seen=" "
  # Each oddsapi* folder on this Mac, and each one already in the backup, so that one gone missing here is reported.
  for d in "$REPO/$p/data/raw"/oddsapi* "$B/$p/data/raw"/oddsapi*; do
    [ -d "$d" ] || continue
    name="${d##*/}"
    case "$seen" in *" $name "*) continue ;; esac
    seen="$seen$name "
    add 1 dir yes "$REPO/$p/data/raw/$name" "$p/data/raw/$name"
  done
done
for p in nfl-weather cfb-weather; do add 2 dir yes "$REPO/$p/data/forward" "$p/data/forward"; done
add 3 dir no "$HOME/.cache/value-finder" "home-cache/value-finder"
add 3 file no "$MDATA/markets.duckdb" "sharp-markets/data/markets.duckdb"
if [ -e "$MDATA/markets.duckdb.wal" ]; then
  add 3 file no "$MDATA/markets.duckdb.wal" "sharp-markets/data/markets.duckdb.wal"
fi
LABEL[1]="Group 1, the paid data"
LABEL[2]="Group 2, the forward-test records"
LABEL[3]="Group 3, slow to re-create"

# ---- a copy on the same disk is not a backup --------------------------------------------------------------------------
# Compare the devices (stat), and the physical disk behind each (diskutil), which also catches a second volume made
# on this Mac's own disk. A network share has no /dev disk, so only its device is compared.
dev_of() { stat -L -f %d "$1" 2>/dev/null; }
whole_disk_of() {
  local node
  node="$(df -P "$1" 2>/dev/null | awk 'NR == 2 { print $1 }')"
  case "$node" in
    /dev/disk*) diskutil info "$node" 2>/dev/null | awk -F': *' '/^ *Part of Whole:/ { print $2; exit }' ;;
  esac
}
DDEV="$(dev_of "$DEST_P")"
DWHOLE="$(whole_disk_of "$DEST_P")"
i=0
while [ $i -lt $N ]; do
  s="${SRC[$i]}"
  if [ -e "$s" ]; then
    [ "$(dev_of "$s")" != "$DDEV" ] ||
      refuse "The destination $DEST is on the same disk as $s. A copy on the same disk is not a backup: if the disk fails, both are lost. Use an external drive or the Mac Studio."
    [ -z "$DWHOLE" ] || [ "$(whole_disk_of "$s")" != "$DWHOLE" ] ||
      refuse "The destination $DEST is another volume of the same physical disk ($DWHOLE) as $s. A copy on the same disk is not a backup: if the disk fails, both are lost. Use an external drive or the Mac Studio."
  fi
  i=$((i + 1))
done

if [ "$CHECK" -eq 0 ]; then
  [ -w "$DEST_P" ] || refuse "The destination $DEST can't be written to. If it is a drive, check that it isn't read-only (in Finder: Get Info, Sharing & Permissions)."
  [ ! -e "$B" ] || [ -w "$B" ] || refuse "The backup folder $B can't be written to."
fi

# ---- helpers -----------------------------------------------------------------------------------------------------------
WORK="$(mktemp -d "${TMPDIR:-/tmp}/vf-backup.XXXXXX")" || { echo "Could not make a temporary folder." >&2; exit 2; }
trap 'rm -rf "$WORK"' EXIT
trap 'exit 130' INT TERM
START="$(date +%s)"
STAMP="$(date -u -r "$START" +%Y-%m-%dT%H%M%SZ)"
# For --check: when the last backup began, from its snapshot's name. A file written on this Mac since then is new or
# changed since the last backup, which the next backup copies; it is listed, and it is not a FAIL.
LAST=0 LASTSHOW=""
if [ "$CHECK" -eq 1 ] && [ -d "$B/forward-snapshots" ]; then
  latest="$(ls "$B/forward-snapshots" | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}Z' | sort | tail -1)"
  if [ -n "$latest" ]; then
    LAST="$(date -j -u -f '%Y-%m-%dT%H%M%SZ' "${latest%%Z*}Z" +%s 2>/dev/null)" || LAST=0
    LASTSHOW="$(date -j -u -f '%Y-%m-%dT%H%M%SZ' "${latest%%Z*}Z" '+%Y-%m-%d %H:%M UTC' 2>/dev/null)"
  fi
fi
if [ -x /sbin/sha256sum ]; then SHA="/sbin/sha256sum"
elif command -v sha256sum >/dev/null 2>&1; then SHA="sha256sum"
else SHA="shasum -a 256"; fi
EXCL=(--exclude=.env --exclude='.env.*' --exclude=.venv --exclude=.git --exclude=.kaggle --exclude=.DS_Store)

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

# Every regular file (or, with "l" as $3, every link) under folder $1, as NUL-separated ./paths in $2, never entering
# the names rsync leaves out (EXCL). Returns non-zero when part of the folder could not be read.
list_paths() {
  ( cd "$1" && find . \( -name .env -o -name '.env.*' -o -name .venv -o -name .git -o -name .kaggle -o -name .DS_Store \) \
      -prune -o -type "${3:-f}" -print0 ) > "$2"
}
# "size<TAB>mtime<TAB>./path" for each path of list $2 that is under folder $1.
stat_list() { ( cd "$1" && xargs -0 stat -f '%z%t%m%t%N' < "$2" ) 2>/dev/null; }
# "files bytes" of a stat_list.
sum_sizes() { awk -F'\t' '{ n++; b += $1 } END { printf "%d %.0f\n", n, b }' "$1"; }

# ---- what is on this Mac now ---------------------------------------------------------------------------------------------
GF[1]=0 GF[2]=0 GF[3]=0 GB[1]=0 GB[2]=0 GB[3]=0
i=0
while [ $i -lt $N ]; do
  nf=0 nb=0
  if [ "${K[$i]}" = dir ] && [ -d "${SRC[$i]}" ]; then
    list_paths "${SRC[$i]}" "$WORK/$i.paths" 2>/dev/null
    stat_list "${SRC[$i]}" "$WORK/$i.paths" > "$WORK/$i.stat"
    read -r nf nb <<EOF
$(sum_sizes "$WORK/$i.stat")
EOF
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
  echo "Checking the backup in $B against $REPO (copying nothing)."
else
  echo "Backing up $REPO to $B."
fi
[ -z "${MARKETS_DATA_DIR:-}${MARKETS_ROOT:-}" ] || echo "The sharp-markets data folder is $MDATA (set by MARKETS_DATA_DIR or MARKETS_ROOT)."
echo
echo "On this Mac now:"
for g in 1 2 3; do
  printf '  %s: %s, %s\n' "${LABEL[$g]}" "$(count "${GF[$g]}" file)" "$(human "${GB[$g]}")"
  i=0
  while [ $i -lt $N ]; do
    if [ "${G[$i]}" = "$g" ]; then
      if [ -e "${SRC[$i]}" ]; then
        printf '      %-44s %15s %10s\n' "$(shown "${SRC[$i]}")" "$(count "${F[$i]}" file)" "$(human "${Z[$i]}")"
      elif [ "${NEED[$i]}" = yes ]; then
        printf '      %-44s not on this Mac\n' "$(shown "${SRC[$i]}")"
      else
        printf '      %-44s not on this Mac (nothing to copy)\n' "$(shown "${SRC[$i]}")"
      fi
    fi
    i=$((i + 1))
  done
done

# ---- space: what a backup writes now (new or changed files, and the snapshot of group 2) --------------------------------
NEEDED="${GB[2]}"
i=0
while [ $i -lt $N ]; do
  if [ -e "${SRC[$i]}" ]; then
    d="$B/${REL[$i]}" n="${Z[$i]}"
    if [ "${K[$i]}" = dir ] && [ -d "$d" ]; then
      # A file is copied again when its size or time differs from the copy's, as rsync decides.
      stat_list "$d" "$WORK/$i.paths" > "$WORK/$i.dstat"
      n="$(awk -F'\t' 'FILENAME == ARGV[1] { have[$0] = 1; next } !($0 in have) { b += $1 } END { printf "%.0f", b }' \
            "$WORK/$i.dstat" "$WORK/$i.stat")"
    elif [ "${K[$i]}" = file ] && [ -f "$d" ] &&
         [ "$(stat -L -f '%z %m' "${SRC[$i]}")" = "$(stat -f '%z %m' "$d")" ]; then
      n=0
    fi
    NEEDED="$(add_num "$NEEDED" "$n")"
  fi
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
SNAPREL=""
if [ "$CHECK" -eq 0 ]; then
  echo
  echo "Copying (nothing on $DEST is deleted):"
  SNAPREL="forward-snapshots/$STAMP"
  k=2
  while [ -e "$B/$SNAPREL" ]; do SNAPREL="forward-snapshots/$STAMP-$k"; k=$((k + 1)); done
  i=0
  while [ $i -lt $N ]; do
    s="${SRC[$i]}" d="$B/${REL[$i]}" g="${G[$i]}" rc=0
    if [ -e "$s" ]; then
      echo "  $(shown "$s")"
      if [ "${K[$i]}" = dir ]; then
        # Archive mode keeps times and copies links as links. There is no --delete of any kind.
        mkdir -p "$d" && rsync -a "${EXCL[@]}" "$s/" "$d/" || rc=$?
        if [ "$g" = 2 ] && [ $rc -eq 0 ]; then
          mkdir -p "$B/$SNAPREL/${REL[$i]}" && rsync -a "${EXCL[@]}" "$s/" "$B/$SNAPREL/${REL[$i]}/" || rc=$?
        fi
      else
        mkdir -p "$(dirname "$d")" && rsync -a "$s" "$d" || rc=$?
      fi
      if [ $rc -ne 0 ]; then
        CF[g]="${CF[$g]}$(printf '1\t%s\t%s' "the copy stopped with an error (code $rc; its message is above)" "${REL[$i]}")"$'\n'
      fi
    fi
    i=$((i + 1))
  done
fi

# ---- compare ---------------------------------------------------------------------------------------------------------
# Inputs, in this order: the source's and the copy's "size<TAB>mtime<TAB>path" lists, their SHA-256 lists (a shasum
# line that starts with a backslash has an escaped name), and their link lists. Prints "1<TAB>what<TAB>path" per problem,
# and "new<TAB>what<TAB>path" for a file written on this Mac since the last backup began (--check only: last > 0).
COMPARE_AWK='
function unesc(s,   o, x, c, len) { o = ""; len = length(s)
  for (x = 1; x <= len; x++) { c = substr(s, x, 1); if (c == "\\" && x < len) { x++; c = substr(s, x, 1); if (c == "n") c = "\n" } o = o c }
  return o }
function hname(line) { return substr(line, 1, 1) == "\\" ? unesc(substr(line, 68)) : substr(line, 67) }
function hval(line) { return substr(line, 1, 1) == "\\" ? substr(line, 2, 64) : substr(line, 1, 64) }
function rest(line) { return substr(line, index(line, "\t") + 1) }
function first(line) { return substr(line, 1, index(line, "\t") - 1) }
function show(p) { sub(/^\.\//, "", p); return under "/" p }
FILENAME == ARGV[1] { r = rest($0); nm = rest(r); ssize[nm] = first($0); smtime[nm] = first(r); order[++nfiles] = nm; next }
FILENAME == ARGV[2] { dsize[rest(rest($0))] = first($0); next }
FILENAME == ARGV[3] { shash[hname($0)] = hval($0); next }
FILENAME == ARGV[4] { dhash[hname($0)] = hval($0); next }
FILENAME == ARGV[5] { slink[rest($0)] = first($0); lorder[++nlinks] = rest($0); next }
FILENAME == ARGV[6] { r = rest($0); dlink[rest(r)] = (substr($0, 1, 1) == "l") ? first(r) : "\001"; next }
END {
  for (x = 1; x <= nfiles; x++) {
    f = order[x]; why = ""
    if (!(f in dsize)) why = "missing on the backup"
    else if (dsize[f] != ssize[f]) why = "differs (size)"
    else if (!(f in shash)) why = "could not be read on this Mac"
    else if (!(f in dhash)) why = "could not be read on the backup"
    else if (dhash[f] != shash[f]) why = "differs (content)"
    if (why != "") {
      if (last + 0 > 0 && smtime[f] + 0 >= last + 0) { printf "new\t%s\t%s\n", "new or changed since the last backup", show(f); continue }
      if (smtime[f] + 0 >= start + 0) why = why ", changed on this Mac while this ran"
      printf "1\t%s\t%s\n", why, show(f)
    }
  }
  for (x = 1; x <= nlinks; x++) {
    f = lorder[x]
    if (!(f in dlink)) printf "1\t%s\t%s\n", "link missing on the backup", show(f)
    else if (dlink[f] != slink[f]) printf "1\t%s\t%s\n", "link differs", show(f)
  }
}'
# Compare source folder $1 with its copy $2, appending problems to $3 with paths shown under $4.
# Sets VF, VB and VL: the source's files, bytes and links.
VN=0
verify_dir() {
  local src="$1" dst="$2" out="$3" under="$4" w
  w="$WORK/v$VN"; VN=$((VN + 1))
  VF=0 VB=0 VL=0
  if ! list_paths "$src" "$w.paths" 2>"$w.err"; then
    printf '1\t%s\t%s\n' "part of it could not be read on this Mac ($(head -1 "$w.err"))" "$under" >> "$out"
  fi
  list_paths "$src" "$w.lpaths" l 2>/dev/null
  stat_list "$src" "$w.paths" > "$w.sstat"
  ( cd "$src" && xargs -0 stat -f '%Y%t%N' < "$w.lpaths" ) > "$w.slinks" 2>/dev/null
  read -r VF VB <<EOF
$(sum_sizes "$w.sstat")
EOF
  VL="$(awk 'END { print NR }' "$w.slinks")"
  if [ ! -d "$dst" ]; then
    [ "$VF" -eq 0 ] && [ "$VL" -eq 0 ] ||
      printf '%s\t%s\t%s\n' "$((VF + VL))" "no copy on the backup yet ($(commas "$VF") files)" "$under" >> "$out"
    return 0
  fi
  stat_list "$dst" "$w.paths" > "$w.dstat"
  ( cd "$src" && xargs -0 $SHA < "$w.paths" ) > "$w.shash" 2>/dev/null
  ( cd "$dst" && xargs -0 $SHA < "$w.paths" ) > "$w.dhash" 2>/dev/null
  ( cd "$dst" && xargs -0 stat -f '%Sp%t%Y%t%N' < "$w.lpaths" ) > "$w.dlinks" 2>/dev/null
  awk -v start="$START" -v last="$LAST" -v under="$under" "$COMPARE_AWK" \
      "$w.sstat" "$w.dstat" "$w.shash" "$w.dhash" "$w.slinks" "$w.dlinks" >> "$out"
}

echo
echo "Comparing every file of groups 1 and 2 on this Mac and on the backup, by size and SHA-256:"
if [ "$CHECK" -eq 1 ] && [ ! -d "$B" ]; then echo "  (There is no backup in $DEST yet: no value-finder-backup folder.)"; fi
FAILED=0 NEWER=0
for g in 1 2; do
  pf="$WORK/problems$g"
  printf '%s' "${CF[$g]}" > "$pf"
  files=0 bytes=0 links=0
  i=0
  while [ $i -lt $N ]; do
    if [ "${G[$i]}" = "$g" ]; then
      if [ ! -d "${SRC[$i]}" ]; then
        [ "${NEED[$i]}" = no ] ||
          printf '1\t%s\t%s\n' "not on this Mac (see \"How to restore\" in ops/BACKUP.md)" "$(shown "${SRC[$i]}")" >> "$pf"
      else
        verify_dir "${SRC[$i]}" "$B/${REL[$i]}" "$pf" "${REL[$i]}"
        files=$((files + VF)) links=$((links + VL))
        bytes="$(add_num "$bytes" "$VB")"
        if [ -n "$SNAPREL" ] && [ "$g" = 2 ]; then
          verify_dir "${SRC[$i]}" "$B/$SNAPREL/${REL[$i]}" "$pf" "$SNAPREL/${REL[$i]}"
        fi
      fi
    fi
    i=$((i + 1))
  done
  what="$(count "$files" file)"
  [ "$links" -eq 0 ] || what="$what and $(count "$links" link)"
  awk -F'\t' '$1 == "new"' "$pf" > "$pf.new"
  awk -F'\t' '$1 != "new"' "$pf" > "$pf.bad"
  nnew="$(awk 'END { print NR }' "$pf.new")"
  NEWER=$((NEWER + nnew))
  if [ ! -s "$pf.bad" ]; then
    where="on the backup"
    [ -z "$SNAPREL" ] || [ "$g" != 2 ] || where="on the backup and in the snapshot $SNAPREL"
    if [ "$nnew" -eq 0 ]; then
      echo "OK    ${LABEL[$g]}: $what, $(exact_bytes "$bytes"); each has the same size and SHA-256 $where."
    else
      echo "OK    ${LABEL[$g]}: $what, $(exact_bytes "$bytes"); each has the same size and SHA-256 $where, except" \
           "$(count "$nnew" file) new or changed on this Mac since the last backup ($LASTSHOW), which the next backup copies:"
    fi
  else
    FAILED=1
    nprob="$(awk -F'\t' '{ s += $1 } END { print s + 0 }' "$pf.bad")"
    echo "FAIL  ${LABEL[$g]} ($what, $(human "$bytes") on this Mac): $(commas "$nprob") missing or different:"
    [ "$nnew" -eq 0 ] || echo "        (and $(count "$nnew" file) new or changed since the last backup, $LASTSHOW, listed after these)"
  fi
  cat "$pf.bad" "$pf.new" |
    awk -F'\t' 'NR <= 20 { printf "        %s: %s\n", $3, $2 } END { if (NR > 20) printf "        ... and %d more lines like these\n", NR - 20 }'
done
if [ "$CHECK" -eq 1 ]; then
  echo "--    ${LABEL[3]}: $(count "${GF[3]}" file), $(human "${GB[3]}") on this Mac; --check does not compare it."
elif [ -n "${CF[3]}" ]; then
  FAILED=1
  echo "FAIL  ${LABEL[3]}: the copy did not finish:"
  printf '%s' "${CF[3]}" | awk -F'\t' '{ printf "        %s: %s\n", $3, $2 }'
else
  echo "--    ${LABEL[3]}: $(count "${GF[3]}" file), $(human "${GB[3]}") copied; not compared file by file (it can be re-created, slowly)."
fi

echo
if [ "$CHECK" -eq 1 ]; then
  if [ $FAILED -ne 0 ]; then echo "Check found problems: read the FAIL lines above (ops/BACKUP.md, \"If a line says FAIL\")."
  elif [ $NEWER -ne 0 ]; then echo "Check finished: groups 1 and 2 match on the backup, apart from what was written on this Mac since the last backup (listed above)."
  else echo "Check finished: groups 1 and 2 match on the backup."; fi
else
  result=OK; [ $FAILED -eq 0 ] || result=FAIL
  printf '%s  %-4s  from %s:%s  group 1: %s, %s; group 2: %s, %s (snapshot %s); group 3: %s, %s\n' \
    "$STAMP" "$result" "$(hostname -s 2>/dev/null)" "$REPO" "$(count "${GF[1]}" file)" "$(human "${GB[1]}")" \
    "$(count "${GF[2]}" file)" "$(human "${GB[2]}")" "$SNAPREL" "$(count "${GF[3]}" file)" "$(human "${GB[3]}")" \
    >> "$B/backup-log.txt" 2>/dev/null || true
  if [ $FAILED -eq 0 ]; then
    echo "Backup finished: groups 1 and 2 match file for file. The forward-test records were also saved as $SNAPREL."
  else
    echo "Backup finished with problems: read the FAIL lines above (ops/BACKUP.md, \"If a line says FAIL\")."
  fi
fi
exit $FAILED
