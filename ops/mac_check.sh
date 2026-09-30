#!/bin/bash
# A read-only check of one Mac for Value Finder: which of the scheduled jobs it runs, whether it could run
# them, and a fingerprint of its data. Written for the move to the Mac Studio (ops/MOVE_TO_NEW_MAC.md); the
# hub runs it at every check-in (.claude/commands/hub.md).
#
#   ops/mac_check.sh --role live                     on the Mac that runs the jobs
#   ops/mac_check.sh --role standby                  on any other Mac: a job loaded there is a FAIL
#   ops/mac_check.sh --role live --tests             also run the four test suites
#   ops/mac_check.sh --role standby --manifest FILE  also write this Mac's counts and hashes to FILE
#   ops/mac_check.sh --role standby --compare FILE   also compare this Mac with a manifest from the other Mac
#   --repo PATH   check the repo at PATH (default ~/code/value-finder)
#   --fetch       run 'git fetch' first, so "behind origin/main" is up to date
#
# It changes nothing. It loads and unloads no job and changes no setting: the only launchctl commands it
# runs are 'list' and 'print'. It writes no file except, with --manifest, that one file. --fetch updates git's
# own copy of GitHub's branches; --tests runs the suites, which write only their temporary files.
# It only reports. The commands it prints (unload, install) are for the owner to run; the hub's check-in
# never runs them for him (.claude/commands/hub.md).
# Keys: it reads each .env file only to learn which names have a value, the way the projects read them
# (the weather projects take only a line that starts NAME=). No value is printed or saved, and the name of
# git's sign-in helper is shown as a label, never as the text it is configured with.
# With --compare, the Mac being checked is the one about to take the jobs over (or back), so a changed file
# that git tracks, or another commit than the other Mac's, is a FAIL there.
# Every line starts OK, WARN or FAIL. The exit status is 0 when nothing failed, 1 when something did, and 2
# for a wrong option. Plain macOS bash (3.2) and the tools macOS ships, plus git.
# For the tests only: MAC_CHECK_LOCALTIME stands in for /etc/localtime, MAC_CHECK_NOW (seconds since 1970)
# for the clock.

PATH="$PATH:/opt/homebrew/bin:/usr/local/bin"
export GIT_OPTIONAL_LOCKS=0          # 'git status' must not rewrite the index
export PYTHONDONTWRITEBYTECODE=1     # no __pycache__ folders from the imports below
unset PYTHONPATH PYTHONHOME PYTHONSTARTUP
NL=$'\n'
TAB=$'\t'

JOBS="com.nflweather.alerts com.cfbweather.alerts com.valuefinder.closecapture com.valuefinder.ledgersync"
# the paid-plan live uses (ops/install_live_uses.sh) spend credits too, so they follow the same one-Mac rule
CREDIT_EXTRAS="com.valuefinder.triggerpoll com.valuefinder.propslog com.valuefinder.nbacollector"
DASHBOARD_JOB="com.valuefinder.dashboard"     # read-only; allowed on either Mac
DATA_FOLDERS="nfl-weather/data cfb-weather/data sharp-markets/data"
CACHE_LABEL="~/.cache/value-finder"
# the forward-test records, hashed file by file: every file in each weather project's data/forward/, the odds
# responses the alert and close jobs saved, and the paid download's own manifest. A *.tmp file is a write in
# progress (runlog.py, board.py and the paid cache write one, then rename it), so it is never a record.
RECORD_ROOTS="nfl-weather/data/forward nfl-weather/data/raw/oddsapi/live cfb-weather/data/forward cfb-weather/data/raw/oddsapi/live sharp-markets/data/raw/_manifest/oddsapi_manifest.csv"
# the paid odds data (sharp-markets/docs/ODDS5M_DAY_ONE.md: data/raw/{sport}/oddsapi/... and data/raw/nba/
# oddsapi_hist/): not a cache, since it can't be had again without paying. Listed file by file with its size.
PAID_GLOB="sharp-markets/data/raw/*/oddsapi*"
REQUIRED_KEYS="ODDS_API_KEY NTFY_TOPIC"       # the names the scheduled jobs read; any other empty name is a WARN
STRICT_ENV="nfl-weather cfb-weather"          # read with line.strip().startswith(NAME + "="); sharp-markets uses python-dotenv
MANIFEST_HEADER="# Value Finder mac_check manifest, version 1 (counts and hashes only: no key, no file content)"
# the times the jobs start by the clock: the four alert runs and the nightly ledger copy (close capture runs
# every 15 minutes, and matters only near a kickoff, which the 3-hour kickoff rule covers)
RUN_TIMES="07:30 11:30 15:30 19:30 23:45"
QUIET_BEFORE=90      # minutes clear before the next run, for a handover of 30 to 60 minutes with room to spare

usage() {
  printf '%s\n' "Usage: ops/mac_check.sh --role live|standby [--repo PATH] [--fetch] [--tests]" \
    "                         [--manifest FILE] [--compare FILE]" \
    "  --role live      this Mac runs the jobs (each missing or unloaded job is a FAIL)" \
    "  --role standby   this Mac must not run them (any job loaded here is a FAIL)" \
    "See the comments at the top of the script and ops/MOVE_TO_NEW_MAC.md."
}

ROLE="" REPO="$HOME/code/value-finder" FETCH=0 TESTS=0 MANIFEST="" COMPARE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --role) ROLE="${2:-}"; shift 2 || { usage; exit 2; } ;;
    --role=*) ROLE="${1#--role=}"; shift ;;
    --repo) REPO="${2:-}"; shift 2 || { usage; exit 2; } ;;
    --repo=*) REPO="${1#--repo=}"; shift ;;
    --manifest) MANIFEST="${2:-}"; shift 2 || { usage; exit 2; } ;;
    --manifest=*) MANIFEST="${1#--manifest=}"; shift ;;
    --compare) COMPARE="${2:-}"; shift 2 || { usage; exit 2; } ;;
    --compare=*) COMPARE="${1#--compare=}"; shift ;;
    --fetch) FETCH=1; shift ;;
    --tests) TESTS=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1"; usage; exit 2 ;;
  esac
done
if [ "$ROLE" != "live" ] && [ "$ROLE" != "standby" ]; then
  printf '%s\n' "Say which Mac this is: --role live (it runs the jobs) or --role standby (it must not)."
  usage; exit 2
fi
if [ -z "$REPO" ]; then usage; exit 2; fi
case "$REPO" in /*) ;; *) REPO="$(pwd)/$REPO" ;; esac
REPO="${REPO%/}"
REPO_P="$( (cd "$REPO" 2>/dev/null && pwd -P) || printf '%s' "$REPO")"
if [ -n "$MANIFEST" ] && [ -n "$COMPARE" ] && [ "$MANIFEST" = "$COMPARE" ]; then
  printf '%s\n' "--manifest and --compare name the same file; use two names."; exit 2
fi

N_OK=0 N_WARN=0 N_FAIL=0
say() {   # say OK|WARN|FAIL "a few plain words"
  case "$1" in
    OK)   N_OK=$((N_OK + 1));     printf 'OK   %s\n' "$2" ;;
    WARN) N_WARN=$((N_WARN + 1)); printf 'WARN %s\n' "$2" ;;
    *)    N_FAIL=$((N_FAIL + 1)); printf 'FAIL %s\n' "$2" ;;
  esac
}
more() { printf '       %s\n' "$1"; }          # a command or a detail that belongs to the line above
section() { printf '\n%s\n' "$1"; }
tilde() { case "$1" in "$HOME"/*) printf '~%s' "${1#$HOME}" ;; *) printf '%s' "$1" ;; esac; }
commas() { printf '%s' "$1" | sed -e :a -e 's/\(.*[0-9]\)\([0-9]\{3\}\)/\1,\2/;ta'; }
human() {  # bytes as the Finder shows them (1 GB = 1,000,000,000 bytes)
  awk -v b="$1" 'BEGIN { if (b >= 1e9) printf "%.1f GB", b / 1e9; else if (b >= 1e6) printf "%.1f MB", b / 1e6;
                         else if (b >= 1e3) printf "%.0f KB", b / 1e3; else printf "%d bytes", b }'
}
# where a path in a job file points: "repo" (the main checkout, where the jobs belong: the repo itself or a
# project or ops folder in it), "worker" (a worker's worktree under .claude/, on another branch and deleted
# when its work merges), "elsewhere" (another place in the repo) or "outside"
job_path_kind() {
  local p="$1" r
  for r in "$REPO" "$REPO_P"; do
    case "$p" in
      "$r") printf repo; return ;;
      "$r"/.claude/*) printf worker; return ;;
      "$r"/nfl-weather|"$r"/cfb-weather|"$r"/sharp-markets|"$r"/dashboard|"$r"/ops) printf repo; return ;;
      "$r"/nfl-weather/*|"$r"/cfb-weather/*|"$r"/sharp-markets/*|"$r"/dashboard/*|"$r"/ops/*) printf repo; return ;;
      "$r"/*) printf elsewhere; return ;;
    esac
  done
  printf outside
}
# a Python that is really there (never Apple's /usr/bin/python3, which asks to install developer tools)
venv_ok() { [ -x "$1/bin/python" ] && [ -d "$(awk -F' = ' '$1 == "home" { print $2; exit }' "$1/pyvenv.cfg" 2>/dev/null)" ]; }
installer_for() {
  case "$1" in
    com.nflweather.alerts) printf 'nfl-weather/scripts/install_alerts.sh' ;;
    com.cfbweather.alerts) printf 'cfb-weather/scripts/install_alerts.sh' ;;
    com.valuefinder.closecapture) printf 'ops/install_close_capture.sh' ;;
    com.valuefinder.ledgersync) printf 'ops/install_ledger_sync.sh' ;;
    com.valuefinder.triggerpoll) printf 'ops/install_live_uses.sh triggerpoll' ;;
    com.valuefinder.propslog) printf 'ops/install_live_uses.sh propslog' ;;
    com.valuefinder.nbacollector) printf 'ops/install_live_uses.sh nbacollector' ;;
    com.valuefinder.dashboard) printf 'ops/install_dashboard.sh' ;;
  esac
}

NOW="${MAC_CHECK_NOW:-$(date +%s)}"
UIDN="$(id -u)"
MODEL="$(system_profiler SPHardwareDataType 2>/dev/null | awk -F': ' '/Model Name/ { print $2; exit }')"
HWMODEL="$(sysctl -n hw.model 2>/dev/null)"
OSV="$(sw_vers -productVersion 2>/dev/null)"
OSB="$(sw_vers -buildVersion 2>/dev/null)"
if [ "$ROLE" = "live" ]; then ROLE_WORDS="the live Mac (it runs the jobs)"; else ROLE_WORDS="a standby Mac (it must not run the jobs)"; fi
printf 'Value Finder check of this Mac as %s\n' "$ROLE_WORDS"
printf '%s (%s), macOS %s; repo %s; %s\n' "${MODEL:-Mac}" "${HWMODEL:-?}" "${OSV:-?}" "$(tilde "$REPO")" \
  "$(date -r "$NOW" '+%a %b %e %Y, %H:%M %Z')"

# Developer tools: without them /usr/bin/git and /usr/bin/swift are placeholders that open an install dialog
# when run, so they are only run when the tools are there.
DEVTOOLS=0
xcode-select -p >/dev/null 2>&1 && DEVTOOLS=1
GIT="$(command -v git 2>/dev/null)"
if [ "$GIT" = "/usr/bin/git" ] && [ $DEVTOOLS -eq 0 ]; then GIT=""; fi
HAVE_REPO=0
if [ -n "$GIT" ] && [ -e "$REPO/.git" ]; then HAVE_REPO=1; fi

# ---------------------------------------------------------------------------------------------------------
section "Jobs: exactly one Mac runs them"
LA="$HOME/Library/LaunchAgents"
LOADED="" PRESENT=""
job_info() {   # the launchd record of a loaded job in this user's session (nothing when it isn't loaded)
  local r
  r="$(launchctl print "gui/$UIDN/$1" 2>/dev/null)" && printf '%s' "$r"
}
lc_field() {   # lc_field "$record" "last exit code": a top-level "key = value" line of a launchd record
  printf '%s\n' "$1" | awk -v k="$2" 'BEGIN { FS = " = " } /^\t[^\t]/ { sub(/^\t/, "");
    if ($1 == k) { sub(/^[^=]*= /, ""); print; exit } }'
}
plist_paths() {  # "kind<TAB>path" for the program, arguments, working folder and logs a job file names
  local f="$1" i=0 v
  while v="$(plutil -extract "ProgramArguments.$i" raw -o - "$f" 2>/dev/null)"; do
    printf 'arg\t%s\n' "$v"; i=$((i + 1)); [ $i -ge 64 ] && break
  done
  v="$(plutil -extract Program raw -o - "$f" 2>/dev/null)" && printf 'arg\t%s\n' "$v"
  v="$(plutil -extract WorkingDirectory raw -o - "$f" 2>/dev/null)" && printf 'dir\t%s\n' "$v"
  v="$(plutil -extract StandardOutPath raw -o - "$f" 2>/dev/null)" && printf 'log\t%s\n' "$v"
  v="$(plutil -extract StandardErrorPath raw -o - "$f" 2>/dev/null)" && printf 'log\t%s\n' "$v"
}
check_job() {   # check_job LABEL KIND   (KIND: core, credit or dashboard)
  local label="$1" kind="$2" f="$LA/$1.plist" rec="" loaded=0 present=0 state pid code sig from words bad=FAIL
  local outside="" worker="" missing="" k p
  [ "$kind" = "dashboard" ] && bad=WARN        # the dashboard only reads: never a FAIL
  [ -f "$f" ] && present=1
  rec="$(job_info "$label")"
  [ -n "$rec" ] && loaded=1
  if [ $loaded -eq 1 ]; then
    state="$(lc_field "$rec" state)"; pid="$(lc_field "$rec" pid)"; code="$(lc_field "$rec" "last exit code")"
    sig="$(lc_field "$rec" "last terminating signal")"; from="$(lc_field "$rec" path)"
    if [ "$state" = "running" ]; then words="loaded, running now${pid:+ (process $pid)}"; else words="loaded, idle"; fi
    if [ -n "$sig" ]; then words="$words, its last run was stopped ($sig)"
    elif [ "$code" = "(never exited)" ]; then words="$words, not run yet"
    elif [ -n "$code" ]; then words="$words, last exit ${code%%:*}"; fi
  fi
  if [ $present -eq 1 ]; then
    if ! plutil -lint -s "$f" >/dev/null 2>&1; then
      say FAIL "$label: its file in ~/Library/LaunchAgents is damaged (not a valid job file)"
      return
    fi
    while IFS="$TAB" read -r k p; do
      case "$p" in /*) ;; *) continue ;; esac
      case "$(job_path_kind "$p")" in
        repo) if [ "$k" != "log" ] && [ ! -e "$p" ]; then missing="${missing:-$p}"; fi ;;
        worker) worker="${worker:-$p}" ;;
        elsewhere) outside="${outside:-$p}" ;;
        *)
          case "$p" in
            /bin/*|/usr/bin/*|/sbin/*|/usr/sbin/*|"$HOME"/Library/Logs/*) ;;
            *) outside="${outside:-$p}" ;;
          esac ;;
      esac
    done < <(plist_paths "$f")
  fi

  if [ "$ROLE" = "standby" ] && [ "$kind" != "dashboard" ]; then
    if [ $loaded -eq 1 ]; then
      say FAIL "$label: $words, on a Mac that is not the live one"
      LOADED="$LOADED $label"
      [ $present -eq 1 ] && PRESENT="$PRESENT $label"
    elif [ $present -eq 1 ]; then
      say FAIL "$label: not loaded, but its file is in ~/Library/LaunchAgents, so it starts at the next login"
      PRESENT="$PRESENT $label"
    elif [ "$kind" = "core" ]; then
      say OK "$label: not installed here, as it should be on a standby Mac"
    fi
    return
  fi

  # live (or the dashboard on either Mac)
  if [ $loaded -eq 0 ] && [ $present -eq 0 ]; then
    if [ "$kind" = "core" ]; then
      say FAIL "$label: not installed on this Mac. If this is the Mac that should run the jobs (and no move is under way), install it:"
      more "$(tilde "$REPO")/$(installer_for "$label")"
    fi
    return
  fi
  if [ $loaded -eq 0 ]; then
    if [ "$kind" = "core" ]; then
      say FAIL "$label: its file is there but it is not loaded, so it will not run. If this is the Mac that should run the jobs, reinstall it:"
      more "$(tilde "$REPO")/$(installer_for "$label")"
    else
      say WARN "$label: its file is there but it is not loaded"
    fi
    return
  fi
  if [ $present -eq 0 ]; then
    say WARN "$label: $words, but its file is not in ~/Library/LaunchAgents, so it will not start after a restart"
    return
  fi
  if [ -n "$from" ] && [ "$from" != "$f" ]; then
    say WARN "$label: $words, loaded from $(tilde "$from") instead of ~/Library/LaunchAgents"
  fi
  if [ -n "$worker" ]; then
    say $bad "$label: $words, but its file points into a worker's folder ($(tilde "$worker")), not the main checkout. Reinstall it from here:"
    more "$(tilde "$REPO")/$(installer_for "$label")"
  elif [ -n "$outside" ]; then
    say $bad "$label: $words, but its file points outside this repo's project folders ($(tilde "$outside")). Reinstall it from here:"
    more "$(tilde "$REPO")/$(installer_for "$label")"
  elif [ -n "$missing" ]; then
    say $bad "$label: $words, but its file names $(tilde "$missing"), which is not there (an environment not built?)"
  elif [ -n "$sig" ] || { [ -n "$code" ] && [ "${code%%:*}" != "0" ] && [ "$code" != "(never exited)" ]; }; then
    say WARN "$label: $words; its file points into this repo. See ops/RUN_RECORDS.md for a failed run"
  else
    say OK "$label: $words; its file points into this repo"
  fi
}

for j in $JOBS; do check_job "$j" core; done
EXTRAS_SEEN=""
for j in $CREDIT_EXTRAS; do
  if [ -f "$LA/$j.plist" ] || [ -n "$(job_info "$j")" ]; then EXTRAS_SEEN="$EXTRAS_SEEN ${j#com.valuefinder.}"; check_job "$j" credit; fi
done
if [ "$ROLE" = "live" ] && [ -z "$EXTRAS_SEEN" ]; then
  say OK "Paid-plan live uses (optional, ops/install_live_uses.sh): none installed"
fi
# The live uses carry two settings in their job files (ops/install_live_uses.sh): a plan tier (free or
# paid) and a credit floor (a number). Neither is a key. Removing the jobs deletes the files, so the check
# prints the command that puts back exactly these jobs with exactly these settings.
live_use_setting() {   # live_use_setting FILE NAME : the value if it has the expected form, else nothing
  local v
  v="$(plutil -extract "EnvironmentVariables.$2" raw -o - "$1" 2>/dev/null)" || return 0
  case "$2:$v" in ODDS_API_TIER:free|ODDS_API_TIER:paid) printf '%s' "$v" ;; ODDS_BACKGROUND_FLOOR:*[!0-9]*|ODDS_BACKGROUND_FLOOR:) ;;
                  ODDS_BACKGROUND_FLOOR:*) printf '%s' "$v" ;; esac
}
if [ "$ROLE" = "live" ] && [ -n "$EXTRAS_SEEN" ]; then
  LU_CMDS="" LU_PREV="" LU_SAME=1 LU_NAMES=""
  for n in $EXTRAS_SEEN; do
    f="$LA/com.valuefinder.$n.plist"
    [ -f "$f" ] || continue
    t="$(live_use_setting "$f" ODDS_API_TIER)"; fl="$(live_use_setting "$f" ODDS_BACKGROUND_FLOOR)"
    pre="${t:+ODDS_API_TIER=$t }${fl:+ODDS_BACKGROUND_FLOOR=$fl }"
    LU_CMDS="$LU_CMDS$pre$(tilde "$REPO")/ops/install_live_uses.sh $n$NL"
    [ -n "$LU_NAMES" ] && [ "$pre" != "$LU_PREV" ] && LU_SAME=0
    LU_PREV="$pre"; LU_NAMES="$LU_NAMES $n"
  done
  if [ -n "$LU_NAMES" ]; then
    say OK "Paid-plan live uses installed:$LU_NAMES. To put back exactly these, with the same settings, after removing them (write this down):"
    if [ $LU_SAME -eq 1 ]; then more "$LU_PREV$(tilde "$REPO")/ops/install_live_uses.sh$LU_NAMES"
    else printf '%s' "$LU_CMDS" | while IFS= read -r l; do more "$l"; done; fi
  fi
fi
if [ -f "$LA/$DASHBOARD_JOB.plist" ] || [ -n "$(job_info "$DASHBOARD_JOB")" ]; then
  check_job "$DASHBOARD_JOB" dashboard
else
  say OK "Dashboard (optional, read-only): not installed"
fi
if [ -d "$HOME/Applications/Value Finder.app" ]; then
  say OK "Menu-bar light (optional, read-only): installed"
fi
# any other job file or loaded job with the project's names
OTHER=""
for f in "$LA"/com.nflweather.*.plist "$LA"/com.cfbweather.*.plist "$LA"/com.valuefinder.*.plist; do
  [ -f "$f" ] || continue
  l="$(basename "$f" .plist)"
  case " $JOBS $CREDIT_EXTRAS $DASHBOARD_JOB " in *" $l "*) ;; *) OTHER="$OTHER $l" ;; esac
done
for l in $(launchctl list 2>/dev/null | awk '$3 ~ /^com\.(nflweather|cfbweather|valuefinder)\./ { print $3 }'); do
  case " $JOBS $CREDIT_EXTRAS $DASHBOARD_JOB $OTHER " in *" $l "*) ;; *) OTHER="$OTHER $l" ;; esac
done
for l in $OTHER; do say WARN "$l: a job with the project's name that this check doesn't know"; done

if [ "$ROLE" = "standby" ] && [ -n "$LOADED$PRESENT" ]; then
  if [ -n "$LOADED" ]; then
    say FAIL "This Mac is not the live one, and it is running the jobs. Unload them now:"
    for l in $LOADED; do more "launchctl bootout gui/$UIDN/$l"; done
  else
    say FAIL "This Mac is not the live one, and its job files are in place: they start at the next login."
  fi
  if [ -n "$PRESENT" ]; then
    more "Then move their files out of ~/Library/LaunchAgents, so they don't start again at the next login:"
    more "mkdir -p ~/value-finder-parked-jobs"
    for l in $PRESENT; do more "mv ~/Library/LaunchAgents/$l.plist ~/value-finder-parked-jobs/"; done
  fi
  more "Then run this check again. Tell the hub which records this Mac may have written (ops/MOVE_TO_NEW_MAC.md)."
fi

# ---------------------------------------------------------------------------------------------------------
section "Clock and power"
LT="${MAC_CHECK_LOCALTIME:-/etc/localtime}"
TZNAME="$(readlink "$LT" 2>/dev/null)"
TZNAME="${TZNAME##*zoneinfo/}"
if [ "$TZNAME" = "America/Los_Angeles" ]; then
  say OK "Time zone America/Los_Angeles: the jobs' 7:30, 11:30, 15:30 and 19:30 are Pacific times"
else
  say FAIL "Time zone is ${TZNAME:-unknown}, not America/Los_Angeles. The jobs run on the Mac's clock, so every run would come at the wrong hour. Set it in System Settings > General > Date & Time"
fi
say OK "macOS ${OSV:-?} (build ${OSB:-?})"

PM_CUSTOM="$(pmset -g custom 2>/dev/null)"
pm_sleep() { printf '%s\n' "$PM_CUSTOM" | awk -v s="$1" '$0 ~ "^"s { on = 1; next } /^[A-Za-z]/ { on = 0 }
                                                     on && $1 == "sleep" { print $2; exit }'; }
AC_SLEEP="$(pm_sleep "AC Power")"
BAT_SLEEP="$(pm_sleep "Battery Power")"
[ -n "$AC_SLEEP" ] || AC_SLEEP="$(pmset -g 2>/dev/null | awk '$1 == "sleep" { print $2; exit }')"
AUTORESTART="$(pmset -g 2>/dev/null | awk '$1 == "autorestart" { print $2; exit }')"
LAPTOP=0
pmset -g batt 2>/dev/null | grep -q InternalBattery && LAPTOP=1
if [ "$ROLE" = "live" ]; then
  if [ $LAPTOP -eq 1 ]; then
    say WARN "This Mac is a laptop: it sleeps when its lid is closed${BAT_SLEEP:+, and on battery after $BAT_SLEEP min}. A run or a close missed while it sleeps is reported as missing, never filled in"
  elif [ "$AC_SLEEP" = "0" ]; then
    say OK "Never goes to sleep by itself"
  else
    say WARN "Goes to sleep after ${AC_SLEEP:-?} min without use. In System Settings > Energy, turn on 'Prevent automatic sleeping when the display is off'"
  fi
  if [ "$AUTORESTART" = "0" ]; then
    say WARN "Will not start again by itself after a power cut ('Start up automatically after a power failure' in System Settings > Energy). After any restart, log in: the jobs run only while you are logged in"
  elif [ "$AUTORESTART" = "1" ]; then
    say OK "Starts again by itself after a power cut (then log in: the jobs run only while you are logged in)"
  elif [ $LAPTOP -eq 0 ]; then
    say WARN "Could not read whether this Mac starts again by itself after a power cut. Look in System Settings > Energy for 'Start up automatically after a power failure'"
  fi
else
  if [ $LAPTOP -eq 1 ]; then say OK "A laptop (sleep matters only on the live Mac)"
  else say OK "Sleep after ${AC_SLEEP:-?} min without use (0 = never; it matters only on the live Mac)"; fi
fi

FREE_KB="$(df -k "$HOME" 2>/dev/null | awk 'NR == 2 { print $4 }')"
if [ -n "$FREE_KB" ]; then
  FREE_B=$((FREE_KB * 1024)); FREE_H="$(human "$FREE_B")"
  if [ "$FREE_B" -lt 10000000000 ]; then
    say FAIL "Only $FREE_H free on the disk. A full disk stops the ledger and the paid download"
  elif [ "$FREE_B" -lt 50000000000 ]; then
    say WARN "$FREE_H free on the disk (under 50 GB). The paid month needs about 3 GB on day one, about 16 GB if F4 is earned"
  else
    say OK "$FREE_H free on the disk"
  fi
else
  say WARN "Could not read the free disk space"
fi

# When is it quiet enough to move the jobs? No run by the clock within 90 minutes (the handover takes 30 to 60
# minutes, and a run that falls inside it doesn't happen at all), none started in the last 10 minutes, and no
# kickoff within 3 hours (close capture needs the jobs at every kickoff). With no kickoff in the ledgers to go
# by, it can't say.
MIN_NOW=$((10#$(date -r "$NOW" +%H) * 60 + 10#$(date -r "$NOW" +%M)))
NEXT_RUN="" TO_NEXT=99999 SINCE_LAST=99999
for t in $RUN_TIMES; do
  m=$((10#${t%:*} * 60 + 10#${t#*:}))
  d=$(( (m - MIN_NOW + 1440) % 1440 )); [ $d -eq 0 ] && d=1440
  if [ $d -lt $TO_NEXT ]; then TO_NEXT=$d; NEXT_RUN="$t"; fi
  s=$(( (MIN_NOW - m + 1440) % 1440 ))
  [ $s -lt $SINCE_LAST ] && SINCE_LAST=$s
done
NEXT_WORDS="Next alert run $NEXT_RUN"
[ "$NEXT_RUN" = "23:45" ] && NEXT_WORDS="Next run by the clock 23:45 (the nightly ledger copy)"
hm() { if [ "$1" -ge 60 ]; then printf '%d h %d min' $(($1 / 60)) $(($1 % 60)); else printf '%d min' "$1"; fi; }
KICK_PY='
import csv, sys, datetime as dt
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")
now = dt.datetime.fromtimestamp(float(sys.argv[1]), dt.timezone.utc)
games = {}
def nfl(r):
    d, t = (r.get("gameday") or "").strip(), (r.get("gametime") or "").strip()
    if not d or not t:
        return None                      # no time set yet
    return dt.datetime.strptime(d + " " + t, "%Y-%m-%d %H:%M").replace(tzinfo=ET)
def cfb(r):
    s, k = (r.get("start_utc") or "").strip(), None
    if s:
        k = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        k = k if k.tzinfo else k.replace(tzinfo=dt.timezone.utc)
    else:
        e, y = (r.get("kick_et") or "").strip(), (r.get("snapshot_utc") or "")[:4]
        k = dt.datetime.strptime(y + " " + e[4:], "%Y %m-%d %H:%M").replace(tzinfo=ET)
    return None if k.astimezone(ET).time() == dt.time(0, 0) else k   # midnight Eastern: no time set yet
for path, sport, when in ((sys.argv[2], "NFL", nfl), (sys.argv[3], "College", cfb)):
    try:
        f = open(path, newline="", encoding="utf-8")
    except OSError:
        continue
    with f:
        for r in csv.DictReader(f):
            try:
                k = when(r)
            except (ValueError, TypeError):
                k = None
            games[(sport, r.get("game_id"))] = (k, sport + ": " + str(r.get("away_team")) + " at " + str(r.get("home_team")))
up = sorted((k, label) for k, label in games.values() if k is not None and k > now)
for k, label in up[:3]:
    loc = k.astimezone()
    print("%d\t%s\t%s %d, %d:%s %s" % (k.timestamp(), label, loc.strftime("%a %b"), loc.day, loc.hour % 12 or 12,
                                       loc.strftime("%M"), "AM" if loc.hour < 12 else "PM"))
'
KPY=""
for v in "$REPO/nfl-weather/.venv" "$REPO/cfb-weather/.venv" "$REPO/dashboard/.venv"; do
  if venv_ok "$v"; then KPY="$v/bin/python"; break; fi
done
KICKS=""
if [ -n "$KPY" ]; then
  KICKS="$("$KPY" -I -B -c "$KICK_PY" "$NOW" "$REPO/nfl-weather/data/forward/ledger.csv" \
           "$REPO/cfb-weather/data/forward/ledger.csv" 2>/dev/null)"
fi
TIMING="$NEXT_WORDS (in $(hm $TO_NEXT))."
QUIET=1 WHY=""
[ $TO_NEXT -lt $QUIET_BEFORE ] && { QUIET=0; WHY="a run starts within $QUIET_BEFORE minutes, and a run due while no Mac has the jobs doesn't happen"; }
[ $SINCE_LAST -lt 10 ] && { QUIET=0; WHY="a run started less than 10 minutes ago and may still be going"; }
if [ -n "$KICKS" ]; then
  K_EPOCH="$(printf '%s\n' "$KICKS" | head -n 1 | cut -f1)"
  K_LABEL="$(printf '%s\n' "$KICKS" | head -n 1 | cut -f2)"
  K_WHEN="$(printf '%s\n' "$KICKS" | head -n 1 | cut -f3)"
  K_MIN=$(( (K_EPOCH - NOW) / 60 ))
  TIMING="$TIMING Next kickoff in the ledgers $K_WHEN, $K_LABEL (in $(hm $K_MIN))."
  if [ $K_MIN -lt 180 ]; then QUIET=0; WHY="${WHY:+$WHY, and }a game kicks off within 3 hours"; fi
elif [ -n "$KPY" ]; then
  TIMING="$TIMING No upcoming kickoff in this Mac's ledgers, so the check can't tell when the next game is."
  [ $QUIET -eq 1 ] && QUIET=2
else
  TIMING="$TIMING Kickoffs not read (no Python environment yet)."
  [ $QUIET -eq 1 ] && QUIET=2
fi
if [ $QUIET -eq 1 ]; then
  say OK "$TIMING A quiet time to move the jobs"
elif [ $QUIET -eq 2 ]; then
  say WARN "$TIMING Not known to be a quiet time: look up the next kickoff before moving the jobs (ops/MOVE_TO_NEW_MAC.md, section 3)"
else
  say WARN "$TIMING Not a quiet time to move the jobs: $WHY"
fi

# ---------------------------------------------------------------------------------------------------------
section "Tools"
if [ -n "$GIT" ]; then
  say OK "$("$GIT" --version 2>/dev/null)"
else
  say FAIL "git is not installed. Installing Homebrew installs Apple's Command Line Tools, which include it (or run: xcode-select --install)"
fi
if command -v gh >/dev/null 2>&1; then
  GH_OUT="$(gh auth status 2>&1)"; GH_RC=$?
  GH_ACCT="$(printf '%s\n' "$GH_OUT" | sed -n 's/.*Logged in to github.com account \([A-Za-z0-9-]*\).*/\1/p' | head -n 1)"
  GH_OUT=""   # never printed: the status text can show part of a token
  if [ $GH_RC -eq 0 ]; then say OK "gh is signed in to GitHub${GH_ACCT:+ as $GH_ACCT}"
  else say WARN "gh is not signed in to GitHub. Run: gh auth login"; fi
else
  say WARN "gh is not installed (brew install gh). The hub uses it for pull requests"
fi
if [ -n "$GIT" ]; then
  # only a label: a helper's configured text can hold a token, and this output is copied into the hub's chat
  HELPER="$("$GIT" config --get-urlmatch credential.helper https://github.com 2>/dev/null | head -n 1)"
  case "$HELPER" in
    "") HLABEL="" ;;
    osxkeychain) HLABEL="the macOS keychain (osxkeychain)" ;;
    *"gh auth git-credential"*) HLABEL="gh (gh auth setup-git)" ;;
    store|"store "*) HLABEL="a plain file on disk (store)" ;;
    cache|"cache "*) HLABEL="git's short-lived memory (cache)" ;;
    manager|manager-core|*git-credential-manager*) HLABEL="Git Credential Manager" ;;
    *) HLABEL="another helper (its text is not shown)" ;;
  esac
  HELPER=""
  if [ -n "$HLABEL" ]; then say OK "git signs in to GitHub with $HLABEL (the nightly ledger copy pushes with it)"
  else say WARN "git has no way to sign in to GitHub, so the nightly ledger copy can't push. Run: gh auth setup-git"; fi
fi
if command -v uv >/dev/null 2>&1; then
  say OK "$(uv --version 2>/dev/null | head -n 1)"
else
  say FAIL "uv is not installed (brew install uv). The environments are built with it"
fi
py_need() {   # the Python a project asks for, from its own files
  local p="$1" v=""
  if [ -f "$REPO/$p/pyproject.toml" ]; then
    v="$(sed -n 's/^requires-python *= *"[>=~]*\([0-9][0-9]*\.[0-9][0-9]*\).*/\1/p' "$REPO/$p/pyproject.toml" | head -n 1)"
    [ -n "$v" ] && { printf '%s pyproject.toml' "$v"; return; }
  fi
  if [ -f "$REPO/$p/README.md" ]; then
    v="$(sed -n 's/.*uv venv[^`]*--python \([0-9][0-9]*\.[0-9][0-9]*\).*/\1/p' "$REPO/$p/README.md" | head -n 1)"
    [ -n "$v" ] && { printf '%s README.md' "$v"; return; }
  fi
  v="$(sed -n 's/.*uv venv.*--python \([0-9][0-9]*\.[0-9][0-9]*\).*/\1/p' "$REPO/ops/cloud_setup.sh" 2>/dev/null | head -n 1)"
  [ -n "$v" ] && printf '%s ops/cloud_setup.sh' "$v"
}
ver_ge() {  # ver_ge 3.12.11 3.12 : is the first version at least the second?
  awk -v a="$1" -v b="$2" 'BEGIN { split(a, x, "."); split(b, y, ".");
    if (x[1] + 0 != y[1] + 0) exit !(x[1] + 0 > y[1] + 0); exit !(x[2] + 0 >= y[2] + 0) }'
}
NEEDS="" NEED_MAX=""
for p in nfl-weather cfb-weather sharp-markets dashboard; do
  n="$(py_need "$p")"
  [ -n "$n" ] || continue
  NEEDS="$NEEDS${NEEDS:+, }$p ${n%% *} (${n#* })"
  if [ -z "$NEED_MAX" ] || ver_ge "${n%% *}" "$NEED_MAX"; then NEED_MAX="${n%% *}"; fi
done
FOUND=""
for d in "$HOME"/.local/share/uv/python/cpython-3.*; do
  [ -d "$d" ] || continue
  v="$(basename "$d" | sed -n 's/^cpython-\([0-9]*\.[0-9]*\.[0-9]*\).*/\1/p')"
  if [ -n "$v" ] && { [ -z "$NEED_MAX" ] || ver_ge "$v" "$NEED_MAX"; }; then FOUND="$FOUND${FOUND:+, }uv's Python $v"; fi
done
for b in /opt/homebrew/bin/python3.* /usr/local/bin/python3.*; do
  [ -x "$b" ] || continue
  v="${b##*python}"
  case "$v" in *[!0-9.]*|"") continue ;; esac
  if [ -z "$NEED_MAX" ] || ver_ge "$v" "$NEED_MAX"; then FOUND="$FOUND${FOUND:+, }$b"; fi
done
if [ -z "$NEEDS" ]; then
  say WARN "Could not read which Python the projects need (no repo here yet?)"
elif [ -n "$FOUND" ]; then
  say OK "Python: $NEEDS; found $FOUND"
else
  say WARN "Python: $NEEDS; none found yet. uv downloads it when it builds the environments"
fi
if [ $DEVTOOLS -eq 1 ] && command -v swift >/dev/null 2>&1; then
  SW="$(swift --version 2>/dev/null | head -n 1)"
  if [ -n "$SW" ]; then say OK "Swift for the menu-bar light: ${SW}"
  else say WARN "Swift is there but did not answer (the Xcode license may need accepting); only the menu-bar light needs it"; fi
else
  say WARN "Swift is not installed. Only the menu-bar light needs it (xcode-select --install)"
fi

# ---------------------------------------------------------------------------------------------------------
section "The repo"
HEAD_SHA=""
if [ ! -d "$REPO" ]; then
  say FAIL "No repo at $(tilde "$REPO")"
elif [ -z "$GIT" ]; then
  say FAIL "Can't look at the repo without git"
elif [ $HAVE_REPO -eq 0 ]; then
  say FAIL "$(tilde "$REPO") is not a git checkout"
else
  if [ "$REPO" != "$HOME/code/value-finder" ] && [ "$REPO_P" != "$( (cd "$HOME/code/value-finder" 2>/dev/null && pwd -P) )" ]; then
    say WARN "The jobs and CLAUDE.md expect the repo at ~/code/value-finder; this check looks at $(tilde "$REPO")"
  fi
  if [ $FETCH -eq 1 ]; then
    if "$GIT" -C "$REPO" fetch --quiet origin 2>/dev/null; then say OK "Fetched from GitHub"
    else say WARN "git fetch failed (no network, or not signed in); the numbers below are as of the last fetch"; fi
  fi
  BR="$("$GIT" -C "$REPO" symbolic-ref --short -q HEAD 2>/dev/null)"
  HEAD_SHA="$("$GIT" -C "$REPO" rev-parse HEAD 2>/dev/null)"
  if [ "$BR" = "main" ]; then
    say OK "On main, at ${HEAD_SHA:0:7}"
  elif [ "$ROLE" = "live" ]; then
    say FAIL "On ${BR:-no branch}, not main. The jobs run whatever is checked out here"
  else
    say WARN "On ${BR:-no branch}, not main"
  fi
  ST="$("$GIT" -C "$REPO" status --porcelain 2>/dev/null)"
  N_CH="$(printf '%s\n' "$ST" | grep -c '^[^?]')"
  N_UN="$(printf '%s\n' "$ST" | grep -c '^??')"
  if [ -z "$ST" ]; then
    say OK "Clean: nothing changed or added outside git"
  elif [ -n "$COMPARE" ] && [ "$N_CH" -gt 0 ]; then
    # the Mac about to take the jobs: a changed tracked file (a data/processed file copied over the committed
    # one, say) means it would run other code or data than git holds
    say FAIL "Not clean: $N_CH files that git tracks are changed here, so this Mac would not run what git holds. Stop and tell the hub. First ones:"
    printf '%s\n' "$ST" | grep '^[^?]' | head -n 5 | while IFS= read -r l; do more "$l"; done
  else
    say WARN "Not clean: $N_CH changed and $N_UN new files that git doesn't track. First ones:"
    printf '%s\n' "$ST" | head -n 3 | while IFS= read -r l; do more "$l"; done
  fi
  if "$GIT" -C "$REPO" rev-parse -q --verify refs/remotes/origin/main >/dev/null 2>&1; then
    AB="$("$GIT" -C "$REPO" rev-list --left-right --count refs/remotes/origin/main...HEAD 2>/dev/null)"
    BEHIND="${AB%%[!0-9]*}"; AHEAD="${AB##*[!0-9]}"
    WHEN="as of the last git fetch"; [ $FETCH -eq 1 ] && WHEN="just fetched"
    if [ "${BEHIND:-0}" = "0" ] && [ "${AHEAD:-0}" = "0" ]; then say OK "Same as origin/main ($WHEN)"
    else say WARN "${BEHIND:-?} commits behind origin/main and ${AHEAD:-?} ahead ($WHEN)"; fi
  else
    say WARN "No origin/main to compare with (run with --fetch)"
  fi
fi

# ---------------------------------------------------------------------------------------------------------
section "Python environments (rebuilt on each Mac, never copied)"
ENV_OK=""
for pp in nfl-weather:nflweather cfb-weather:cfbweather sharp-markets:markets dashboard:vfdash; do
  p="${pp%%:*}" pkg="${pp#*:}" v="$REPO/${pp%%:*}/.venv"
  sev=FAIL; [ "$p" = "dashboard" ] && sev=WARN
  [ -d "$REPO/$p" ] || continue
  if [ ! -x "$v/bin/python" ]; then
    say $sev "$p: no environment. Build it (ops/MOVE_TO_NEW_MAC.md, 'Rebuild the environments')"
    continue
  fi
  home="$(awk -F' = ' '$1 == "home" { print $2; exit }' "$v/pyvenv.cfg" 2>/dev/null)"
  if [ -z "$home" ] || [ ! -d "$home" ]; then
    say $sev "$p: its environment points to a Python that isn't on this Mac (copied from another Mac?). Rebuild it"
    continue
  fi
  pv="$("$v/bin/python" -I -B -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null)"
  need="$(py_need "$p")"; need="${need%% *}"
  if [ -n "$need" ] && ! ver_ge "${pv:-0.0}" "$need"; then
    say $sev "$p: Python ${pv:-?} in its environment, but it needs $need or newer. Rebuild it"
    continue
  fi
  if (cd "$REPO/$p" && "$v/bin/python" -B -c "import $pkg") >/dev/null 2>&1; then
    say OK "$p: Python $pv, imports $pkg"
    ENV_OK="$ENV_OK $p"
  else
    say $sev "$p: Python $pv, but it can't import $pkg. Rebuild it"
  fi
done

if [ $TESTS -eq 1 ]; then
  section "Test suites"
  for p in nfl-weather cfb-weather sharp-markets dashboard; do
    sev=FAIL; [ "$p" = "dashboard" ] && sev=WARN      # like its environment: the dashboard is optional
    case " $ENV_OK " in *" $p "*) ;; *) say $sev "$p tests: not run (no working environment)"; continue ;; esac
    t0=$(date +%s)
    # no -q here: two projects already set it, and twice leaves out the "N passed" line
    OUT="$(cd "$REPO/$p" && "$REPO/$p/.venv/bin/python" -B -m pytest -p no:cacheprovider tests 2>&1)"; RC=$?
    secs=$(( $(date +%s) - t0 ))
    SUM="$(printf '%s\n' "$OUT" | grep -E '[0-9]+ (passed|failed|error|errors|skipped)|no tests ran' | tail -n 1 |
           sed -e 's/^=* *//' -e 's/ *=*$//' -e 's/ in [0-9.]*s.*$//')"
    case $RC in
      0) say OK "$p tests: ${SUM:-passed} ($secs s)" ;;
      1) say FAIL "$p tests: ${SUM:-some failed} ($secs s). Failed:"
         printf '%s\n' "$OUT" | grep -E '^(FAILED|ERROR) ' | head -n 5 | while IFS= read -r l; do more "$l"; done ;;
      5) say WARN "$p tests: none found" ;;
      *) say FAIL "$p tests: could not run (exit $RC): $(printf '%s\n' "$OUT" | tail -n 1 | cut -c1-160)" ;;
    esac
  done
fi

# ---------------------------------------------------------------------------------------------------------
section "Keys (names only; no value is ever shown)"
# A .env line is read the way its project reads it. The weather projects (nflweather/oddsapi.py, notify._env,
# quota.py, cfbweather/notify._env) take a name's value only from a line that, spaces trimmed, starts NAME=;
# they strip spaces and quotes from the value, and the last such line wins. They skip 'export NAME=...' and
# 'NAME = ...'. sharp-markets reads its .env with python-dotenv, which takes those forms too.
# env_line LINE STRICT sets _K (A: an assignment the project reads, F: a line it skips, empty: neither), _N
# (the name) and _V (the value as the project would use it). Callers clear _V; nothing prints it.
env_line() {
  local t="$1"
  _K="" _N="" _V=""
  t="${t%$'\r'}"
  t="${t#"${t%%[![:space:]]*}"}"; t="${t%"${t##*[![:space:]]}"}"
  if [ "$2" = "1" ]; then
    if [[ "$t" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
      _K=A _N="${BASH_REMATCH[1]}" _V="${BASH_REMATCH[2]}"
      _V="${_V#"${_V%%[![:space:]]*}"}"; _V="${_V%"${_V##*[![:space:]]}"}"
      while [ "${_V#\"}" != "$_V" ]; do _V="${_V#\"}"; done; while [ "${_V%\"}" != "$_V" ]; do _V="${_V%\"}"; done
      while [ "${_V#\'}" != "$_V" ]; do _V="${_V#\'}"; done; while [ "${_V%\'}" != "$_V" ]; do _V="${_V%\'}"; done
    elif [[ "$t" =~ ^export[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*= ]] ||
         [[ "$t" =~ ^([A-Za-z_][A-Za-z0-9_]*)[[:space:]]+= ]]; then
      _K=F _N="${BASH_REMATCH[1]}"
    fi
  elif [[ "$t" =~ ^(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=[[:space:]]*(.*)$ ]]; then
    _K=A _N="${BASH_REMATCH[2]}" _V="${BASH_REMATCH[3]}"
    case "$_V" in
      \"*) _V="${_V#\"}"; _V="${_V%%\"*}" ;;
      \'*) _V="${_V#\'}"; _V="${_V%%\'*}" ;;
      \#*) _V="" ;;
      *) _V="${_V%%[[:space:]]#*}"; _V="${_V%"${_V##*[![:space:]]}"}" ;;
    esac
  fi
  t=""
  [[ x =~ x ]]                                   # leaves no value behind in BASH_REMATCH
}
env_strict() { case " $STRICT_ENV " in *" $1 "*) printf 1 ;; *) printf 0 ;; esac; }
# env_names FILE STRICT: one line per assignment, "A<TAB>NAME<TAB>STATE", or "F<TAB>NAME<TAB>-" for a line
# the project skips. STATE: 1 (a value), 0 (empty, or only a comment), S (a space inside the value, which the
# weather jobs would keep as part of it).
env_names() {
  local line st
  while IFS= read -r line || [ -n "$line" ]; do
    env_line "$line" "$2"
    case "$_K" in
      A) case "$_V" in
           "") st=0 ;;
           \#*) st=0 ;;
           *[[:space:]]*) if [ "$2" = "1" ]; then st=S; else st=1; fi ;;
           *) st=1 ;;
         esac
         printf 'A\t%s\t%s\n' "$_N" "$st" ;;
      F) printf 'F\t%s\t-\n' "$_N" ;;
    esac
    _V=""
  done < "$1"
  line=""
}
# env_state FILE STRICT: "NAME<TAB>STATE<TAB>SKIPPED" per name. STATE is the last readable line's (1, 0 or
# S), or F when the project can read no line for it. SKIPPED is 1 when some line for it is one it skips.
env_state() {
  env_names "$1" "$2" | awk -F'\t' '$1 == "A" { v[$2] = $3; seen[$2] = 1 } $1 == "F" { f[$2] = 1; seen[$2] = 1 }
    END { for (n in seen) print n "\t" ((n in v) ? v[n] : "F") "\t" ((n in f) ? 1 : 0) }'
}
env_value_same() {  # env_value_same NAME FILE... : 0 when every file gives NAME the same non-empty value, as its project reads it
  local name="$1" first="" f cur line strict
  shift
  for f in "$@"; do
    cur=""
    strict="$(env_strict "$(basename "$(dirname "$f")")")"
    while IFS= read -r line || [ -n "$line" ]; do
      env_line "$line" "$strict"
      [ "$_K" = "A" ] && [ "$_N" = "$name" ] && cur="$_V"
      _V=""
    done < "$f"
    line=""
    [ -n "$cur" ] || { first=""; return 1; }
    if [ -z "$first" ]; then first="$cur"; elif [ "$cur" != "$first" ]; then cur=""; first=""; return 1; fi
  done
  cur=""; first=""
  return 0
}
KEY_LINES=""
ENV_FILES=""
for p in nfl-weather cfb-weather sharp-markets; do
  f="$REPO/$p/.env" ex="$REPO/$p/.env.example"
  [ -d "$REPO/$p" ] || continue
  if [ ! -f "$f" ]; then
    say FAIL "$p/.env is missing. Copy it from the other Mac (never by AirDrop or a cloud drive)"
    continue
  fi
  ENV_FILES="$ENV_FILES$f$NL"
  MODE="$(stat -f '%Lp' "$f" 2>/dev/null)"; OWNER="$(stat -f '%u' "$f" 2>/dev/null)"
  PRIVATE=0
  if [ "$OWNER" != "$UIDN" ]; then
    say FAIL "$p/.env belongs to another user"
  elif [ -z "$MODE" ] || [ $(( 8#$MODE & 077 )) -ne 0 ]; then
    say FAIL "$p/.env can be read by others (mode $MODE). Make it yours only:"
    more "chmod 600 $(tilde "$f")"
  else
    PRIVATE=1
  fi
  if [ ! -r "$f" ]; then
    say FAIL "$p/.env can't be read, even by you (mode $MODE). Make it readable by you only:"
    more "chmod 600 $(tilde "$f")"
    continue
  fi
  STRICT="$(env_strict "$p")"
  STATE="$(env_state "$f" "$STRICT")"
  SET="" EMPTY_REQ="" EMPTY_OPT="" SKIPPED="" SPACE_REQ="" SPACE_OPT="" EXTRA=""
  NAMES="$(sed -n 's/^[[:space:]]*\(export[[:space:]]\{1,\}\)\{0,1\}\([A-Za-z_][A-Za-z0-9_]*\)[[:space:]]*=.*/\2/p' "$ex" 2>/dev/null)"
  for n in $NAMES; do
    st="$(printf '%s\n' "$STATE" | awk -F'\t' -v n="$n" '$1 == n { print $2 " " $3; exit }')"
    req=0; case " $REQUIRED_KEYS " in *" $n "*) req=1 ;; esac
    case "$st" in
      "1 1") SET="$SET${SET:+,}$n"; EXTRA="$EXTRA $n" ;;
      "1 "*) SET="$SET${SET:+,}$n" ;;
      "F "*) SKIPPED="$SKIPPED $n" ;;
      "S "*) if [ $req -eq 1 ]; then SPACE_REQ="$SPACE_REQ $n"; else SPACE_OPT="$SPACE_OPT $n"; fi ;;
      *) if [ $req -eq 1 ]; then EMPTY_REQ="$EMPTY_REQ $n"; else EMPTY_OPT="$EMPTY_OPT $n"; fi ;;
    esac
  done
  KEY_LINES="${KEY_LINES}keys$TAB$p$TAB$SET$NL"
  if [ -n "$EMPTY_REQ" ]; then
    say FAIL "$p/.env has no value for:$EMPTY_REQ (the jobs need it)"
  fi
  if [ -n "$SKIPPED" ]; then
    say FAIL "$p/.env writes$SKIPPED as 'export NAME=…' or 'NAME = …'. This project reads only lines of the form NAME=value, so to it there is no value. Rewrite each such line as NAME=value, with no 'export' and no spaces around the = sign"
  fi
  if [ -n "$SPACE_REQ" ]; then
    say FAIL "$p/.env has a space inside the value of:$SPACE_REQ (a comment after it?). The jobs use everything after the = sign, spaces and all. Put only the value after NAME="
  fi
  if [ -n "$SPACE_OPT" ]; then
    say WARN "$p/.env has a space inside the value of:$SPACE_OPT (a comment after it?). The project would use everything after the = sign"
  fi
  if [ -n "$EXTRA" ]; then
    say WARN "$p/.env also has a line for$EXTRA written as 'export NAME=…' or 'NAME = …', which this project skips. The NAME=value line is the one it uses; delete the other"
  fi
  if [ -n "$EMPTY_OPT" ]; then
    say WARN "$p/.env has no value for:$EMPTY_OPT (not used by the scheduled jobs)"
  fi
  if [ -z "$EMPTY_REQ$SKIPPED$SPACE_REQ" ] && [ $PRIVATE -eq 1 ]; then
    SHOWN="${SET//,/, }"
    say OK "$p/.env: yours only (mode $MODE); values set for ${SHOWN:-no name}"
  fi
done
N_ENV="$(printf '%s' "$ENV_FILES" | grep -c .)"
if [ "$N_ENV" -ge 2 ]; then
  OLDIFS="$IFS"; IFS="$NL"
  # shellcheck disable=SC2086
  if env_value_same ODDS_API_KEY $ENV_FILES; then
    say OK "ODDS_API_KEY is the same in all $N_ENV .env files, as each project reads it (they share one credit file)"
  else
    say WARN "ODDS_API_KEY is not the same in every .env file, as each project reads it. The projects share one credit file; ODDS5M_DAY_ONE.md puts the same key in all three"
  fi
  IFS="$OLDIFS"
fi
KAGGLE="$HOME/.kaggle/access_token"
if [ -f "$KAGGLE" ]; then
  KM="$(stat -f '%Lp' "$KAGGLE" 2>/dev/null)"
  if [ "$KM" = "600" ]; then say OK "~/.kaggle/access_token: there, mode 600"; KAGGLE_STATE="present"
  else say FAIL "~/.kaggle/access_token has mode $KM, not 600:"; more "chmod 600 ~/.kaggle/access_token"; KAGGLE_STATE="present"; fi
else
  say WARN "~/.kaggle/access_token is not there (only the Kaggle download for H3 needs it)"; KAGGLE_STATE="missing"
fi

# ---------------------------------------------------------------------------------------------------------
section "Registered files (the frozen pricing cohorts)"
# The registered hash is over the cohort's residuals (market.cohort_hash), not the file's bytes. The code's
# own check is market.pricing_cohort(board.PRICING_COHORT_SHA256), which raises on a cohort that was never
# registered. Importing <pkg>.config makes the project's data folders, and this check writes nothing, so it
# gives market.py a config module that only names them.
COHORT_PY='
import importlib, re, sys, types
from pathlib import Path
proj, pkg = Path(sys.argv[1]), sys.argv[2]
cfg = types.ModuleType(pkg + ".config")
cfg.ROOT, cfg.RAW, cfg.PROC = proj, proj / "data" / "raw", proj / "data" / "processed"
sys.modules[pkg + ".config"] = cfg
sys.path.insert(0, str(proj))
m = re.search(r"PRICING_COHORT_SHA256\s*=\s*.([0-9a-f]{64}).", (proj / pkg / "board.py").read_text())
if not m:
    print("NOREG"); sys.exit()
reg = m.group(1)
prereg = "yes" if reg in (proj / "PREREGISTRATION.md").read_text() else "no"
try:
    resid = importlib.import_module(pkg + ".market").pricing_cohort(reg)
except Exception as e:
    print("BAD", reg, prereg, type(e).__name__ + ": " + " ".join(str(e).split())[:160]); sys.exit()
print("OK", reg, prereg, len(resid))
'
COHORT_LINES=""
for pp in nfl-weather:nflweather cfb-weather:cfbweather; do
  p="${pp%%:*}" pkg="${pp#*:}" f="$REPO/${pp%%:*}/data/processed/pricing_cohort.json"
  [ -d "$REPO/$p" ] || continue
  if [ ! -f "$f" ]; then say FAIL "$p: data/processed/pricing_cohort.json is missing"; continue; fi
  FSHA="$(shasum -a 256 "$f" | cut -c1-64)"
  COHORT_LINES="${COHORT_LINES}cohort$TAB$p$TAB$FSHA$NL"
  if [ $HAVE_REPO -eq 1 ] && [ -n "$("$GIT" -C "$REPO" status --porcelain -- "$p/data/processed/pricing_cohort.json" 2>/dev/null)" ]; then
    say FAIL "$p: pricing_cohort.json differs from the committed file. Changing it needs a dated amendment"
  fi
  case " $ENV_OK " in
    *" $p "*)
      R="$(cd "$REPO/$p" && "$REPO/$p/.venv/bin/python" -B -c "$COHORT_PY" "$REPO/$p" "$pkg" 2>&1 | tail -n 1)"
      set -f; set -- $R; set +f
      if [ "$1" = "OK" ]; then
        if [ "$3" = "yes" ]; then
          say OK "$p: the code's own check passes ($4 games; registered hash ${2:0:12}, as in PREREGISTRATION.md). File sha256 ${FSHA:0:12}"
        else
          say WARN "$p: the code's own check passes (registered hash ${2:0:12}), but PREREGISTRATION.md doesn't show that hash. File sha256 ${FSHA:0:12}"
        fi
      elif [ "$1" = "BAD" ]; then
        shift 3; say FAIL "$p: the pricing cohort is not the registered one: $*"
      else
        say FAIL "$p: could not run the code's own cohort check: $(printf '%s' "$R" | cut -c1-160)"
      fi
      set -- ;;
    *) say WARN "$p: pricing_cohort.json sha256 ${FSHA:0:12}; the code's own check needs the environment" ;;
  esac
done

# ---------------------------------------------------------------------------------------------------------
section "Data and forward-test records"
# Left out everywhere: .DS_Store, and *.tmp, a write in progress that the code renames at once (a copy can
# catch one, and rsync never deletes it afterwards). A file whose name holds a tab, a line break or a
# backslash can't be written into the manifest's lines, so it is reported, not fingerprinted.
odd_names() {  # odd_names PATH... (relative to the current folder): such names, one per line, shown with ? for the odd character
  find "$@" \( -name "*${TAB}*" -o -name "*${NL}*" -o -name '*\\*' \) -print0 2>/dev/null | tr '\000\n\t\\' '\n???'
}
FOLDER_LINES=""
folder() {    # folder LABEL PATH
  local label="$1" d="$2" n b dg
  if [ -L "$d" ]; then
    say FAIL "$label is a link to another place ($(tilde "$(readlink "$d")")), not a folder. rsync copies a link as a link, so its files would not reach the other Mac. Tell the hub"
    return
  fi
  if [ ! -d "$d" ]; then say FAIL "$label is missing on this Mac"; return; fi
  # the count from NUL-separated names (right even for a name with a line break); the fingerprint from each
  # file's name and size, so two Macs at the same commit agree although git set other file times
  n="$(cd "$d" && find . -type f ! -name .DS_Store ! -name '*.tmp' -print0 2>/dev/null | tr -cd '\000' | wc -c | tr -d ' ')"
  b="$(cd "$d" && find . -type f ! -name .DS_Store ! -name '*.tmp' -exec stat -f '%z' {} + 2>/dev/null | awk '{ s += $1 } END { printf "%.0f", s }')"
  dg="$(cd "$d" && find . -type f ! -name .DS_Store ! -name '*.tmp' -exec stat -f "%N${TAB}%z" {} + 2>/dev/null | LC_ALL=C sort | shasum -a 256 | cut -c1-64)"
  FOLDER_LINES="${FOLDER_LINES}folder$TAB$label$TAB${n:-0}$TAB${b:-0}$TAB$dg$NL"
  say OK "$label: $(commas "${n:-0}") files, $(human "${b:-0}")"
}
if [ -d "$REPO" ]; then
  for d in $DATA_FOLDERS; do folder "$d" "$REPO/$d"; done
fi
folder "$CACHE_LABEL" "$HOME/.cache/value-finder"

RECORD_LINES="" PAID_LINES=""
if [ -d "$REPO" ]; then
  ROOTS=""
  for r in $RECORD_ROOTS; do
    if [ -L "$REPO/$r" ]; then
      say FAIL "$r is a link to another place ($(tilde "$(readlink "$REPO/$r")")), not the records themselves. rsync copies a link as a link, so these records would not reach the other Mac, and the check can't fingerprint them. Tell the hub"
      continue
    fi
    [ -e "$REPO/$r" ] && ROOTS="$ROOTS $r"
  done
  PAID_ROOTS=""
  for r in "$REPO"/$PAID_GLOB; do
    [ -e "$r" ] || [ -L "$r" ] || continue
    r="${r#"$REPO"/}"
    case "$r" in sharp-markets/data/raw/_manifest/*) continue ;; esac     # the download's own log: a record above
    if [ -L "$REPO/$r" ]; then
      say FAIL "$r (paid odds data) is a link to another place, not the files themselves. rsync would copy only the link. Tell the hub"
      continue
    fi
    PAID_ROOTS="$PAID_ROOTS $r"
  done
  if [ -n "$ROOTS$PAID_ROOTS" ]; then
    # shellcheck disable=SC2086
    ODD="$(cd "$REPO" && odd_names $ROOTS $PAID_ROOTS)"
    # shellcheck disable=SC2086
    LINKS="$( (cd "$REPO" && find $ROOTS -type l 2>/dev/null) | head -n 3)"
    if [ -n "$ODD" ]; then
      say FAIL "$(printf '%s\n' "$ODD" | grep -c .) record or paid files have a tab, a line break or a backslash in their name (shown as ?), so the check can't fingerprint them. Tell the hub:"
      printf '%s\n' "$ODD" | head -n 3 | while IFS= read -r l; do more "$l"; done
    fi
    if [ -n "$LINKS" ]; then
      say FAIL "Some records are links to other files, not the files themselves, so they would not reach the other Mac. Tell the hub:"
      printf '%s\n' "$LINKS" | while IFS= read -r l; do more "$l"; done
    fi
  fi
  if [ -n "$ROOTS" ]; then
    # shellcheck disable=SC2086
    RECORD_LINES="$(cd "$REPO" && {
        find $ROOTS -type f ! -name .DS_Store ! -name '*.tmp' ! -name "*${TAB}*" ! -name "*${NL}*" ! -name '*\\*' \
          -exec shasum -a 256 {} + 2>/dev/null | awk '{ print "H\t" substr($0, 67) "\t" $1 }'
        find $ROOTS -type f ! -name .DS_Store ! -name '*.tmp' ! -name "*${TAB}*" ! -name "*${NL}*" ! -name '*\\*' \
          -exec stat -f "S${TAB}%N${TAB}%z${TAB}%m" {} + 2>/dev/null
      } | awk -F'\t' -v OFS='\t' '$1 == "H" { h[$2] = $3; next } { s[$2] = $3; m[$2] = $4 }
                                  END { for (p in s) print "record", p, h[p], s[p], m[p] }' | LC_ALL=C sort)"
    [ -n "$RECORD_LINES" ] && RECORD_LINES="$RECORD_LINES$NL"
  fi
  if [ -n "$PAID_ROOTS" ]; then
    # too big to hash at every check (3 GB on day one, 16 GB with F4), so each file's size and time
    # shellcheck disable=SC2086
    PAID_LINES="$(cd "$REPO" && find $PAID_ROOTS -type f ! -name .DS_Store ! -name '*.tmp' ! -name "*${TAB}*" ! -name "*${NL}*" \
                    ! -name '*\\*' -exec stat -f "paid${TAB}%N${TAB}%z${TAB}%m" {} + 2>/dev/null | LC_ALL=C sort)"
    [ -n "$PAID_LINES" ] && PAID_LINES="$PAID_LINES$NL"
  fi
  NPAID="$(printf '%s' "$PAID_LINES" | grep -c '^paid')"
  if [ "$NPAID" -gt 0 ]; then
    PB="$(printf '%s' "$PAID_LINES" | awk -F'\t' '{ s += $3 } END { printf "%.0f", s }')"
    say OK "Paid odds data (not a cache: it can't be had again without paying): $(commas "$NPAID") files, $(human "$PB"), each listed with its size"
  fi
  for p in nfl-weather cfb-weather; do
    fw="$REPO/$p/data/forward"
    [ -d "$REPO/$p" ] || continue
    if [ ! -d "$fw" ]; then say FAIL "$p/data/forward is missing: no forward-test records on this Mac"; continue; fi
    NF="$(printf '%s' "$RECORD_LINES" | awk -F'\t' -v pre="$p/data/forward/" 'index($2, pre) == 1 { n++ } END { print n + 0 }')"
    NO="$(printf '%s' "$RECORD_LINES" | awk -F'\t' -v pre="$p/data/raw/oddsapi/live/" 'index($2, pre) == 1 { n++ } END { print n + 0 }')"
    if [ ! -f "$fw/ledger.csv" ]; then say FAIL "$p/data/forward/ledger.csv is missing"; continue; fi
    LROWS=$(( $(wc -l < "$fw/ledger.csv") - 1 ))
    RUNS_WORDS="no runs.csv"
    if [ -f "$fw/runs.csv" ]; then
      RROWS=$(( $(wc -l < "$fw/runs.csv") - 1 ))
      LAST="$(awk -F, 'NR == 1 { for (i = 1; i <= NF; i++) { if ($i == "run_utc") a = i; if ($i == "status") b = i }; next }
                       NF { l = $a " (" $b ")" } END { print l }' "$fw/runs.csv")"
      RUNS_WORDS="runs.csv $(commas "$RROWS") rows, the last run ${LAST:-none}"
    fi
    say OK "$p records: $NF files in data/forward and $NO saved odds responses, hashed; ledger.csv $(commas "$LROWS") rows; $RUNS_WORDS"
  done
fi

# ---------------------------------------------------------------------------------------------------------
CUR="$MANIFEST_HEADER${NL}written_utc$TAB$(date -u -r "$NOW" +%Y-%m-%dT%H:%M:%SZ)${NL}mac$TAB${MODEL:-Mac} (${HWMODEL:-?}), macOS ${OSV:-?}${NL}repo_head$TAB${HEAD_SHA:-none}$NL$FOLDER_LINES$RECORD_LINES$PAID_LINES$COHORT_LINES${KEY_LINES}kaggle$TAB$KAGGLE_STATE"

if [ -n "$COMPARE" ]; then
  section "Compared with the other Mac's manifest"
  if [ ! -f "$COMPARE" ] || [ "$(head -n 1 "$COMPARE" 2>/dev/null)" != "$MANIFEST_HEADER" ]; then
    say FAIL "$COMPARE is not a manifest written by ops/mac_check.sh"
  else
    while IFS="$TAB" read -r st msg; do
      [ -n "$st" ] || continue
      if [ "$st" = "MORE" ]; then more "$msg"; else say "$st" "$msg"; fi
    done < <(printf '%s\n' "$CUR" | awk -F'\t' '
      function hb(b) { return b >= 1e9 ? sprintf("%.1f GB", b / 1e9) : b >= 1e6 ? sprintf("%.1f MB", b / 1e6) : sprintf("%d bytes", b) }
      function out(s, m) { print s "\t" m; if (s != "OK") bad++ }
      FNR == NR { if ($1 == "folder") { of[$2] = 1; on[$2] = $3; ob[$2] = $4; od[$2] = $5; oorder[++nof] = $2 }
                  else if ($1 == "record") { orc[$2] = 1; oh[$2] = $3; om[$2] = $5; rorder[++nor] = $2 }
                  else if ($1 == "paid") { opd[$2] = 1; ops[$2] = $3; opm[$2] = $4; porder[++nop] = $2 }
                  else if ($1 == "cohort") oc[$2] = $3
                  else if ($1 == "keys") { ok_[$2] = 1; okeys[$2] = $3 }
                  else if ($1 == "repo_head") ohead = $2
                  else if ($1 == "written_utc") owritten = $2
                  else if ($1 == "mac") omac = $2
                  next }
      $1 == "folder" { cf[$2] = 1; cn[$2] = $3; cb[$2] = $4; cd[$2] = $5; corder[++ncf] = $2 }
      $1 == "record" { crc[$2] = 1; ch[$2] = $3; cm[$2] = $5; crorder[++ncr] = $2 }
      $1 == "paid" { cpd[$2] = 1; cps[$2] = $3; cpm[$2] = $4; cporder[++ncp] = $2 }
      $1 == "cohort" { cc[$2] = $3 }
      $1 == "keys" { ck_[$2] = 1; ckeys[$2] = $3 }
      $1 == "repo_head" { chead = $2 }
      END {
        for (i = 1; i <= nor; i++) { p = rorder[i]
          if (!(p in crc)) { out("FAIL", "Record missing here: " p); rbad++ }
          else if (ch[p] != oh[p]) { out("FAIL", "Record differs from the other Mac: " p " (sha256 here " substr(ch[p], 1, 12) ", there " substr(oh[p], 1, 12) ")"); rbad++ }
          else if (cm[p] != om[p]) out("WARN", "Record has the same content but another file time: " p " (copied without keeping times?)")
          else same++ }
        for (i = 1; i <= ncr; i++) { p = crorder[i]
          if (!(p in orc)) { out("FAIL", "Record here that the other Mac does not have: " p); rbad++ } }
        if (nor == 0) { out("FAIL", "The other Mac'"'"'s manifest lists no forward-test records, so it proves nothing. Write it again there"); rbad++ }
        for (i = 1; i <= nop; i++) { p = porder[i]
          if (!(p in cpd)) { out("FAIL", "Paid odds file missing here: " p); pbad++ }
          else if (cps[p] != ops[p]) { out("FAIL", "Paid odds file has another size here: " p " (" cps[p] " bytes here, " ops[p] " there)"); pbad++ }
          else if (cpm[p] != opm[p]) out("WARN", "Paid odds file has the same size but another file time: " p " (copied without keeping times?)") }
        for (i = 1; i <= ncp; i++) { p = cporder[i]
          if (!(p in opd)) out("WARN", "Paid odds file here that the other Mac does not list: " p) }
        for (i = 1; i <= nof; i++) { p = oorder[i]
          if (!(p in cf)) out("FAIL", "Folder missing here: " p)
          else if (cn[p] != on[p] || cb[p] != ob[p])
            out("WARN", "Folder differs: " p " has " cn[p] " files (" hb(cb[p]) ") here and " on[p] " (" hb(ob[p]) ") there")
          else if (cd[p] != od[p]) out("WARN", "Folder has the same number of files and bytes, but other file names or sizes: " p)
        }
        for (i = 1; i <= ncf; i++) { p = corder[i]; if (!(p in of)) out("WARN", "Folder here that the other manifest does not list: " p) }
        for (p in oc) if (!(p in cc)) out("FAIL", "Pricing cohort missing here: " p)
                      else if (cc[p] != oc[p]) out("FAIL", "Pricing cohort file differs from the other Mac: " p)
        for (p in ok_) {
          if (!(p in ck_)) { out("WARN", "Keys: no " p "/.env here to compare"); continue }
          n = split(okeys[p], a, ","); for (j = 1; j <= n; j++) if (a[j] != "" && index("," ckeys[p] ",", "," a[j] ",") == 0)
            out("WARN", "Keys: " p "/.env has a value for " a[j] " on the other Mac but not here")
          n = split(ckeys[p], a, ","); for (j = 1; j <= n; j++) if (a[j] != "" && index("," okeys[p] ",", "," a[j] ",") == 0)
            out("WARN", "Keys: " p "/.env has a value for " a[j] " here but not on the other Mac")
        }
        if (ohead == "" || ohead == "none" || chead == "" || chead == "none")
          out("WARN", "Can'"'"'t tell whether the two repos are at the same commit (no git on one of them)")
        else if (ohead != chead)
          out("FAIL", "The repo is at another commit here (" substr(chead, 1, 7) ") than on the other Mac (" substr(ohead, 1, 7) "), so this Mac would run other code. Run git pull --ff-only on both Macs, then write the other Mac'"'"'s manifest again and compare again (ops/MOVE_TO_NEW_MAC.md)")
        if (nor && !rbad) out("OK", "Records: all " nor " forward-test records are here, the same byte for byte as on the other Mac")
        else if (same) print "MORE\t" same " other records are the same byte for byte."
        if (nop && !pbad) out("OK", "Paid odds data: all " nop " files are here, each the same size as on the other Mac")
        if (!bad) out("OK", "Same as the manifest written " owritten " on " omac ": " (nor + 0) " records byte for byte, " (nop + 0) " paid files, " (nof + 0) " folders, the cohorts, the key names and the commit")
      }' "$COMPARE" -)
  fi
fi

if [ -n "$MANIFEST" ]; then
  section "Manifest"
  if [ -e "$MANIFEST" ] && [ "$(head -n 1 "$MANIFEST" 2>/dev/null)" != "$MANIFEST_HEADER" ]; then
    say FAIL "$MANIFEST already exists and is not a manifest; not overwritten. Choose another name"
  elif printf '%s\n' "$CUR" > "$MANIFEST" 2>/dev/null; then
    NREC="$(printf '%s' "$RECORD_LINES" | grep -c '^record')"
    NFOL="$(printf '%s' "$FOLDER_LINES" | grep -c '^folder')"
    NPD="$(printf '%s' "$PAID_LINES" | grep -c '^paid')"
    say OK "Written to $(tilde "$MANIFEST"): $NREC records, $NPD paid files and $NFOL folders, counts and hashes only (no key, no file content)"
  else
    say FAIL "Could not write $MANIFEST"
  fi
fi

printf '\nSummary: %d OK, %d WARN, %d FAIL.' "$N_OK" "$N_WARN" "$N_FAIL"
if [ "$N_FAIL" -eq 0 ]; then printf ' Nothing failed.\n'; exit 0; fi
printf ' Something failed: see the FAIL lines above.\n'
exit 1
