"""Record the closing total for each kickoff slot (PREREGISTRATION.md, amendment 2).

Runs every 15 minutes (ops/capture_closes.sh, launchd). When FBS games kick off in
2–20 minutes and that kickoff time hasn't been captured yet, one Odds API call
(1 credit) records the current total and prices for every game in the slot:
Pinnacle when it lists the game, else DraftKings, as on the board. Rows are appended
to data/forward/closes.csv. A slot that fails (no key, quota low, API down) is
retried on the next run while it's still inside the window, and otherwise stays
missing: score_forward.py reports missing closes and never imputes them.

    python scripts/capture_close.py [--now 2026-10-01T23:50:00Z]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from cfbweather import fetch
from cfbweather.board import odds_team_names
from cfbweather.build import schedules
from cfbweather.config import ROOT

WINDOW = (pd.Timedelta(minutes=2), pd.Timedelta(minutes=20))
FWD = ROOT / "data" / "forward"
CLOSES, STATE = FWD / "closes.csv", FWD / "close_state.json"

ap = argparse.ArgumentParser()
ap.add_argument("--now", help="pretend it's this UTC time (testing)")
args = ap.parse_args()
now = pd.Timestamp(args.now) if args.now else pd.Timestamp.now(tz="UTC")

s = schedules()
s = s[(s.season == s.season.max()) & ~s.tbd & s.home_points.isna()]
if "home_division" in s:
    s = s[s.home_division.astype(str).str.lower().eq("fbs") | s.away_division.astype(str).str.lower().eq("fbs")]
state = json.loads(STATE.read_text()) if STATE.exists() else {"captured": []}
due = s[(s.start_utc - now).between(*WINDOW)]
slots = sorted({t.strftime("%Y-%m-%dT%H:%MZ") for t in due.start_utc} - set(state["captured"]))
if not slots:
    sys.exit()

due = due[due.start_utc.dt.strftime("%Y-%m-%dT%H:%MZ").isin(slots)]
oa = fetch.odds_api_totals(odds_team_names()).dropna(subset=["home_team", "away_team"])
if oa.empty:
    sys.exit(print(f"{now:%Y-%m-%d %H:%M}Z close capture: no prices for {', '.join(slots)}; will retry inside the window"))
got = due[["game_id", "start_utc", "home_team", "away_team"]].merge(
    oa.drop(columns="commence_utc"), on=["home_team", "away_team"], how="left")
rows = got.rename(columns={"mkt_total": "close_total", "mkt_under": "close_under", "mkt_over": "close_over",
                           "quote_utc": "capture_utc"})
rows["start_utc"] = rows.start_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
cols = ["capture_utc", "game_id", "start_utc", "home_team", "away_team", "line_src", "close_total", "close_under",
        "close_over"]
FWD.mkdir(parents=True, exist_ok=True)
rows[cols].to_csv(CLOSES, mode="a", header=not CLOSES.exists(), index=False)
state["captured"] = sorted(set(state["captured"]) | set(slots))
STATE.write_text(json.dumps(state))
print(f"{now:%Y-%m-%d %H:%M}Z close capture: {int(rows.close_total.notna().sum())}/{len(rows)} games priced "
      f"for {', '.join(slots)}")
