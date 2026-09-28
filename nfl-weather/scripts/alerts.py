"""Weather betting alerts, tiered to match STRATEGY.md. Meant to run on a schedule
(scripts/install_alerts.sh sets up a macOS launchd job). Each run refreshes the
schedule, forecasts and lines, then alerts once per event:

RULE B (the forward-tested betting rule; see STRATEGY.md for stakes)
  WIND UNDER   outdoor game, kickoff wind forecast >= 15 mph, 1-3 days out, AND a posted
               total with an under price no worse than -115 and positive expected value
               at that line and price (board.rule_b_status == "SIGNAL"). Otherwise nothing
               actionable is sent; a wind trigger without a usable price is a WATCH.
  LINE LAG     same gates, plus the kickoff wind forecast rose >= 5 mph since the last
               check while a total present at both checks moved less than half a point.

WATCH (paper-track only; log them, don't bet them yet)
  MODEL LEAN   pre-registered rule: model P(under) >= 55% (or <= 45% for overs).
  EDGE         model vs the de-vigged price >= 5 points.
  COLD VISITOR dome or warm-climate visitor, forecast <= 32F: home side / visitor team-total under.

Delivery: macOS notification, plus an iPhone push when NTFY_TOPIC is set in .env.
State lives in data/forward/alert_state.json so nothing is sent twice.

    python scripts/alerts.py              # normal run
    python scripts/alerts.py --dry-run    # print what would be sent (nflverse lines; no Odds API credit)
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
up = board.compute(days=args.days, refresh=True, pinnacle=oddsapi.has_key() and not args.dry_run)
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

    # RULE B: only a full signal (trigger + horizon + posted line + acceptable price + positive EV) is actionable
    price = "" if pd.isna(r.mkt_under) else f" at {r.mkt_under:+.0f}"
    if r.rule_b == "SIGNAL":
        storm = " (rain/snow also forecast)" if wet else ""
        shop = (f" Best under at this number: {r.best_under:+.0f} ({r.best_under_book})."
                if pd.notna(r.best_under) and pd.notna(r.mkt_under) and r.best_under > r.mkt_under else "")
        fire("ruleb", f"RULE B WIND UNDER {r.mkt_total:.1f}{price}: {game}",
             f"{detail}{storm}. Expected value {100 * r.ev_under:+.1f}% at this line and price.{shop} "
             f"Bet only this number or better; paper-log the price you actually get.", s)
    elif r.rule_b in ("no_price", "price_too_high", "negative_ev"):
        fire(f"ruleb_{r.rule_b}", f"WATCH wind {r.wx_wind:.0f} mph, no bet ({r.rule_b.replace('_', ' ')}): {game}",
             detail + f"{price}. Rule B needs a posted total, an under price of -115 or better, and positive EV.", s)

    # RULE B: forecast jumped while a posted total sat still (both totals must exist)
    w_prev, t_prev = s.get("wind"), s.get("total")
    if (r.rule_b == "SIGNAL" and w_prev is not None and r.wx_wind - w_prev >= 5
            and t_prev is not None and abs(r.mkt_total - t_prev) < 0.5):
        fire(f"lag{round(r.wx_wind)}", f"RULE B LINE LAG {r.mkt_total:.1f}{price}: {game}",
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
    if pd.notna(r.wx_temp) and r.wx_temp <= 32 and warm_vis and 1 <= r.lead_days <= 3:
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
