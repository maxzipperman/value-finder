"""College football alerts for the two pre-registered rules (see STRATEGY.md):

  Rule B   only a full signal is actionable; a 15+ mph wind forecast without a usable
           price arrives as WATCH.
  Rule HT  high-total under, paper only. It is graded at the last quote before kickoff,
           so it alerts only on the last scheduled run before the game (kickoff within
           HT_ALERT_H hours), telling you to take the latest number.

Mac notification plus the same iPhone ntfy topic as the NFL alerts.
State: data/forward/alert_state.json.

    python scripts/alerts.py [--dry-run | --test]    # --dry-run: ESPN prices only, no Odds API credit
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from cfbweather import board, notify
from cfbweather.config import ROOT

ap = argparse.ArgumentParser()
ap.add_argument("--dry-run", action="store_true")
ap.add_argument("--test", action="store_true")
args = ap.parse_args()
if args.test:
    ok = notify.send("CFB weather alerts", "Test alert: notifications are working.")
    sys.exit(print("mac notification sent;", "phone push sent" if ok else "no phone push (NTFY_TOPIC not set)"))

STATE = ROOT / "data" / "forward" / "alert_state.json"
STATE.parent.mkdir(parents=True, exist_ok=True)
state = json.loads(STATE.read_text()) if STATE.exists() else {}
up = board.compute(odds=not args.dry_run)
if up.empty:
    sys.exit(print("no FBS games in the next 8 days"))
if not args.dry_run:
    board.save(up)
HT_ALERT_H = 4.5   # runs are 4 hours apart, so this is the last scheduled check before kickoff
now = pd.Timestamp.now(tz="UTC")
alerts = []
for r in up.itertuples():
    if r.rule_ht == "SIGNAL" and (r.start_utc - now) <= pd.Timedelta(hours=HT_ALERT_H):
        s = state.setdefault(str(r.game_id), {"sent": []})
        if "ht" not in s["sent"]:
            s["sent"].append("ht")
            alerts.append((f"CFB HIGH TOTAL UNDER {r.mkt_total:.1f} at {r.mkt_under:+.0f} (paper): {r.away_team} @ "
                           f"{r.home_team} {r.kick_et} ET",
                           f"Total is at least {r.ht_threshold:.1f} (last season's mean + 10). Rule HT takes the "
                           f"latest number before kickoff; paper only through 2027 (PREREGISTRATION.md)."))
for r in up.itertuples():
    s = state.setdefault(str(r.game_id), {"sent": []})
    game = f"{r.away_team} @ {r.home_team} {r.kick_et} ET"
    if r.rule_b == "SIGNAL":
        key, title = "ruleb", f"CFB RULE B WIND UNDER {r.mkt_total:.1f} at {r.mkt_under:+.0f}: {game}"
        shop = (f" Best under at this number: {r.best_under:+.0f} ({r.best_under_book})."
                if pd.notna(r.best_under) and r.best_under > r.mkt_under else "")
        body = (f"{r.wx_wind:.0f} mph, {r.wx_temp:.0f}°F forecast {r.lead_days}d out; EV {100 * r.ev_under:+.1f}% "
                f"at this line ({r.line_src}).{shop} Bet only this number or better; log your fill.")
    elif r.rule_b in ("no_price", "price_too_high", "negative_ev"):
        key, title = f"watch_{r.rule_b}", f"CFB WATCH wind {r.wx_wind:.0f} mph, no bet ({r.rule_b.replace('_', ' ')}): {game}"
        body = "Rule B needs a posted total, an under price of -115 or better, and positive EV."
    else:
        continue
    if key not in s["sent"]:
        s["sent"].append(key)
        alerts.append((title, body))
for title, body in alerts:
    print(f"ALERT  {title}\n       {body}")
    if not args.dry_run:
        notify.send(title, body)
if not alerts:
    print(f"{pd.Timestamp.now(tz='UTC'):%Y-%m-%d %H:%M}Z checked {len(up)} FBS games, nothing new")
if not args.dry_run:
    STATE.write_text(json.dumps(state, indent=1))
