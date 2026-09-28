"""Weather betting alerts, tiered to match STRATEGY.md. Meant to run on a schedule
(scripts/install_alerts.sh sets up a macOS launchd job). Each run refreshes the
schedule, forecasts and lines, then alerts once per event:

BET (the one rule with a real-money case)
  WIND UNDER   outdoor game, kickoff wind forecast >= 15 mph, 1-3 days out.
               Upgrades to STORM UNDER (1.5 units) when rain/snow is also forecast.
  LINE LAG     the kickoff wind forecast rose >= 5 mph since the last check (to 15+)
               while the total moved less than half a point.

WATCH (paper-track only; log them, don't bet them yet)
  MODEL LEAN   pre-registered rule: model P(under) >= 55% (or <= 45% for overs).
  EDGE         model vs the de-vigged price >= 5 points.
  COLD VISITOR dome or warm-climate visitor, forecast <= 32F: home side / visitor team-total under.

Delivery: macOS notification, plus an iPhone push when NTFY_TOPIC is set in .env.
State lives in data/forward/alert_state.json so nothing is sent twice.

    python scripts/alerts.py              # normal run
    python scripts/alerts.py --dry-run    # print what would be sent
    python scripts/alerts.py --test       # send one test notification
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from nflweather import board, notify, oddsapi
from nflweather.config import ROOT
from nflweather.features import RAIN_IN, SNOW_IN

WIND_BET, MAX_LEAD = 15, 3

ap = argparse.ArgumentParser()
ap.add_argument("--dry-run", action="store_true")
ap.add_argument("--test", action="store_true")
ap.add_argument("--days", type=int, default=8)
ap.add_argument("--edge", type=float, default=0.05)
args = ap.parse_args()

if args.test:
    ok = notify.send("NFL weather alerts", "Test alert: notifications are working.")
    print("mac notification sent;", "phone push sent" if ok else "no phone push (NTFY_TOPIC not set)")
    sys.exit()

STATE = ROOT / "data" / "forward" / "alert_state.json"
STATE.parent.mkdir(parents=True, exist_ok=True)
state = json.loads(STATE.read_text()) if STATE.exists() else {}
up = board.compute(days=args.days, refresh=True, pinnacle=oddsapi.has_key())
now = pd.Timestamp.now(tz="UTC")
if up.empty:
    print(f"{now:%Y-%m-%d %H:%M}Z no games in the next {args.days} days")
    sys.exit()
if not args.dry_run:
    board.save(up)
kick = pd.to_datetime(up.gameday + " " + up.gametime).dt.tz_localize("America/New_York").dt.tz_convert("UTC")
up = up[(kick > now) & (up.wx_src == "era5")]

alerts = []


def fire(key, title, body, s):
    """Send each (game, trigger) once; `key` changes when the trigger escalates."""
    if key in s.setdefault("sent", []):
        return
    s["sent"].append(key)
    alerts.append((title, body))


for r in up.itertuples():
    s = state.setdefault(r.game_id, {})
    game = f"{r.away_team} @ {r.home_team} {r.gameday[5:]} {r.gametime} ET"
    total = "–" if pd.isna(r.mkt_total) else f"{r.mkt_total:.1f} ({r.line_src})"
    detail = f"{r.conditions}; total {total}; forecast {r.lead_days}d out"
    wet = (r.wx_precip or 0) >= RAIN_IN or (r.wx_snow or 0) >= SNOW_IN

    # BET: wind under (storm upgrade)
    if pd.notna(r.wx_wind) and r.wx_wind >= WIND_BET and r.lead_days <= MAX_LEAD:
        if wet:
            fire("storm", f"BET 1.5u STORM UNDER: {game}", detail + ". Take the best under number now.", s)
        else:
            fire("wind", f"BET 1u WIND UNDER: {game}", detail + ". Take the best under number now.", s)

    # BET: forecast jumped while the total sat still
    w_prev, t_prev = s.get("wind"), s.get("total")
    if w_prev is not None and pd.notna(r.wx_wind) and r.wx_wind >= WIND_BET and r.wx_wind - w_prev >= 5:
        flat = t_prev is None or pd.isna(r.mkt_total) or abs(r.mkt_total - t_prev) < 0.5
        if flat:
            fire(f"lag{round(r.wx_wind)}", f"BET LINE LAG: {game}",
                 f"Kickoff wind {w_prev:.0f} → {r.wx_wind:.0f} mph since the last check; total still {total}.", s)

    # WATCH: pre-registered model lean and model-vs-market edge
    side = "UNDER" if r.lean.startswith("UNDER") else "OVER" if r.lean.startswith("OVER") else ""
    if side:
        mk = f" vs market {100 * r.p_market:.0f}%" if pd.notna(r.p_market) else ""
        fire(f"lean{side}", f"WATCH model {side.lower()}: {game}",
             f"{detail}; model P(under) {100 * r.p_under:.0f}%{mk}. Paper only (PREREGISTRATION.md).", s)
    elif pd.notna(r.edge) and abs(r.edge) >= args.edge:
        fire("edge", f"WATCH edge {100 * r.edge:+.0f} pts: {game}", detail + ". Paper only.", s)

    # WATCH: cold-weather visitor from a dome or a warm week
    warm_vis = (r.v_dome == 1) or (pd.notna(r.v_city_temp7) and r.v_city_temp7 >= 60)
    if pd.notna(r.wx_temp) and r.wx_temp <= 32 and warm_vis and r.lead_days <= MAX_LEAD:
        why = "dome team" if r.v_dome == 1 else f"home week {r.v_city_temp7:.0f}°F"
        fire("coldvis", f"WATCH cold visitor ({why}): {game}",
             detail + ". Home side / visitor team-total under. Paper only.", s)

    s["wind"] = None if pd.isna(r.wx_wind) else round(float(r.wx_wind), 1)
    s["total"] = None if pd.isna(r.mkt_total) else float(r.mkt_total)
    s["seen_utc"] = now.strftime("%Y-%m-%dT%H:%MZ")

for title, body in alerts:
    print(f"ALERT  {title}\n       {body}")
    if not args.dry_run:
        notify.send(title, body)
if not alerts:
    print(f"{now:%Y-%m-%d %H:%M}Z checked {len(up)} outdoor games, nothing new")
if not args.dry_run:
    STATE.write_text(json.dumps(state, indent=1))
