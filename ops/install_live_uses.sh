#!/bin/zsh
# Install (or remove) the launchd jobs for the paid-plan live uses (strategy-research/odds-api-credits.md,
# "After the month: live uses"; details in ops/LIVE_USES.md). All three are logging only and GET-only.
# They don't touch the alert, close-capture or ledger jobs.
#
#   com.valuefinder.triggerpoll   every 10 min  ops/poll_triggers.sh   NFL + CFB prices while a Rule B wind trigger is active
#   com.valuefinder.propslog      every 15 min  nfl-weather/scripts/log_props.py   NFL props, alternates, team totals
#   com.valuefinder.nbacollector  every minute  sharp-markets `markets --sport nba collect`   PLAN.md section 7, from Oct 20
#
# Each job sets ODDS_QUOTA_KIND=background: it calls the Odds API only on a paid plan, and stops at the
# background floor (max(2,000, 2% of the plan); quota.py), so the alerts and close capture keep their credits.
#
#   ops/install_live_uses.sh                     install / reinstall all three
#   ops/install_live_uses.sh triggerpoll propslog  install some
#   ops/install_live_uses.sh --remove            uninstall all three
#   ODDS_API_TIER=paid ODDS_BACKGROUND_FLOOR=150000 ops/install_live_uses.sh
#                                                install with the overrides written into each plist
#
# ODDS_API_TIER (free|paid) and ODDS_BACKGROUND_FLOOR (credits) are read by quota.py and the collector
# from the process environment only; the weather projects never load .env into it. So when either is
# set in the environment that runs this script, it is written into every plist's EnvironmentVariables.
# Unset, the jobs use the defaults (tier from the plan size; floor max(2,000, 2% of the plan)).
# Rerun the script to change or drop them.
#
# The three projects share one quota file, so installing refuses unless ODDS_API_KEY is the same in
# nfl-weather/.env, cfb-weather/.env and sharp-markets/.env (the keys are compared, never printed).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$HOME/Library/Logs"
ALL=(triggerpoll propslog nbacollector)

env_key() {   # ODDS_API_KEY from a .env file: the last assignment, quotes and spaces stripped
  [[ -f "$1" ]] || return 0
  sed -n -E 's/^[[:space:]]*(export[[:space:]]+)?ODDS_API_KEY[[:space:]]*=//p' "$1" | tail -n 1 | tr -d "\"' \t\r"
}

remove=0
wanted=()
for a in "$@"; do
  if [[ "$a" == "--remove" ]]; then remove=1; else wanted+=("$a"); fi
done
(( ${#wanted[@]} )) || wanted=("${ALL[@]}")

envxml="<key>ODDS_QUOTA_KIND</key><string>background</string>"
if [[ -n "${ODDS_API_TIER:-}" ]]; then
  [[ "$ODDS_API_TIER" == "free" || "$ODDS_API_TIER" == "paid" ]] || { echo "ODDS_API_TIER must be free or paid"; exit 1; }
  envxml+="<key>ODDS_API_TIER</key><string>$ODDS_API_TIER</string>"
fi
if [[ -n "${ODDS_BACKGROUND_FLOOR:-}" ]]; then
  [[ "$ODDS_BACKGROUND_FLOOR" =~ ^[0-9]+$ ]] || { echo "ODDS_BACKGROUND_FLOOR must be a whole number of credits"; exit 1; }
  envxml+="<key>ODDS_BACKGROUND_FLOOR</key><string>$ODDS_BACKGROUND_FLOOR</string>"
fi

if (( ! remove )); then
  first=""
  for proj in nfl-weather cfb-weather sharp-markets; do
    k="$(env_key "$ROOT/$proj/.env")"
    if [[ -z "$k" ]]; then echo "refusing to install: no ODDS_API_KEY in $proj/.env"; exit 1; fi
    if [[ -z "$first" ]]; then
      first="$k"
    elif [[ "$k" != "$first" ]]; then
      echo "refusing to install: ODDS_API_KEY in $proj/.env differs from nfl-weather/.env."
      echo "Put the same (paid) key in all three .env files first; the projects share one quota file."
      exit 1
    fi
  done
fi

for job in "${wanted[@]}"; do
  case "$job" in
    triggerpoll)  interval=600; args=("/bin/bash" "$ROOT/ops/poll_triggers.sh"); wd="$ROOT" ;;
    propslog)     interval=900; args=("$ROOT/nfl-weather/.venv/bin/python" "$ROOT/nfl-weather/scripts/log_props.py"); wd="$ROOT/nfl-weather" ;;
    nbacollector) interval=60;  args=("$ROOT/sharp-markets/.venv/bin/markets" "--sport" "nba" "collect"); wd="$ROOT/sharp-markets" ;;
    *) echo "unknown job $job (choose from ${ALL[*]})"; exit 1 ;;
  esac
  LABEL="com.valuefinder.$job"
  PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  if (( remove )); then rm -f "$PLIST"; echo "removed $LABEL"; continue; fi
  mkdir -p "$HOME/Library/LaunchAgents" "$LOGS"
  argxml=""
  for x in "${args[@]}"; do argxml+="<string>$x</string>"; done
  cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>$argxml</array>
  <key>WorkingDirectory</key><string>$wd</string>
  <key>EnvironmentVariables</key><dict>$envxml</dict>
  <key>StartInterval</key><integer>$interval</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$LOGS/valuefinder-$job.log</string>
  <key>StandardErrorPath</key><string>$LOGS/valuefinder-$job.log</string>
</dict></plist>
PLIST
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  echo "installed $LABEL (every ${interval}s; env: ODDS_QUOTA_KIND=background${ODDS_API_TIER:+ ODDS_API_TIER=$ODDS_API_TIER}${ODDS_BACKGROUND_FLOOR:+ ODDS_BACKGROUND_FLOOR=$ODDS_BACKGROUND_FLOOR}; log: ~/Library/Logs/valuefinder-$job.log)"
done
