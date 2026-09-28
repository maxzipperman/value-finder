"""Record Pinnacle's closing total for each kickoff slot (PREREGISTRATION.md, amendment 3).

Runs every 15 minutes (ops/capture_closes.sh, launchd). When NFL games kick off in
2–20 minutes and that kickoff time hasn't been captured yet, one Odds API call
(1 credit) records Pinnacle's current total and prices for every game in the slot.
Rows are appended to data/forward/closes.csv. A slot that fails (no key, quota low,
API down) is retried on the next run while it's still inside the window, and
otherwise stays missing: score_forward.py reports missing closes and never imputes them.

    python scripts/capture_close.py [--now 2026-10-09T00:05:00Z]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from nflweather import oddsapi
from nflweather.config import RAW, ROOT

WINDOW = (pd.Timedelta(minutes=2), pd.Timedelta(minutes=20))
FWD = ROOT / "data" / "forward"
CLOSES, STATE = FWD / "closes.csv", FWD / "close_state.json"

ap = argparse.ArgumentParser()
ap.add_argument("--now", help="pretend it's this UTC time (testing)")
args = ap.parse_args()
now = pd.Timestamp(args.now) if args.now else pd.Timestamp.now(tz="UTC")

g = pd.read_csv(RAW / "games.csv")
g = g[g.result.isna() & g.gametime.notna()].copy()
g["kick_utc"] = pd.to_datetime(g.gameday + " " + g.gametime).dt.tz_localize("America/New_York").dt.tz_convert("UTC")
state = json.loads(STATE.read_text()) if STATE.exists() else {"captured": []}
due = g[(g.kick_utc - now).between(*WINDOW)]
slots = sorted({t.strftime("%Y-%m-%dT%H:%MZ") for t in due.kick_utc} - set(state["captured"]))
if not slots:
    sys.exit()

due = due[due.kick_utc.dt.strftime("%Y-%m-%dT%H:%MZ").isin(slots)]
try:
    pin = oddsapi.live(markets=("totals",))
except SystemExit as e:
    sys.exit(print(f"{now:%Y-%m-%d %H:%M}Z close capture: no prices for {', '.join(slots)} ({e}); "
                   "will retry inside the window"))
pin = pin[pin.market == "totals"].rename(columns={"home": "home_team", "away": "away_team", "total": "close_total",
                                                  "under_price": "close_under", "over_price": "close_over",
                                                  "snapshot_utc": "capture_utc"})
rows = due[["game_id", "kick_utc", "home_team", "away_team"]].merge(
    pin[["home_team", "away_team", "capture_utc", "book", "close_total", "close_under", "close_over", "book_update"]],
    on=["home_team", "away_team"], how="left")
rows["kick_utc"] = rows.kick_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
FWD.mkdir(parents=True, exist_ok=True)
rows.to_csv(CLOSES, mode="a", header=not CLOSES.exists(), index=False)
state["captured"] = sorted(set(state["captured"]) | set(slots))
STATE.write_text(json.dumps(state))
print(f"{now:%Y-%m-%d %H:%M}Z close capture: {int(rows.close_total.notna().sum())}/{len(rows)} games priced "
      f"for {', '.join(slots)}")
