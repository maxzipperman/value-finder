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
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$HOME/Library/Logs"
ALL=(triggerpoll propslog nbacollector)

remove=0
wanted=()
for a in "$@"; do
  if [[ "$a" == "--remove" ]]; then remove=1; else wanted+=("$a"); fi
done
(( ${#wanted[@]} )) || wanted=("${ALL[@]}")

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
  <key>EnvironmentVariables</key><dict><key>ODDS_QUOTA_KIND</key><string>background</string></dict>
  <key>StartInterval</key><integer>$interval</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$LOGS/valuefinder-$job.log</string>
  <key>StandardErrorPath</key><string>$LOGS/valuefinder-$job.log</string>
</dict></plist>
PLIST
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  echo "installed $LABEL (every ${interval}s; log: ~/Library/Logs/valuefinder-$job.log)"
done
