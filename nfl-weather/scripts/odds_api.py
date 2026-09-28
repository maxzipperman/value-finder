"""Pinnacle lines from The Odds API.

    python scripts/odds_api.py plan                          # free: snapshot schedule + credit estimate
    python scripts/odds_api.py backfill --confirm --max-credits 9000
    python scripts/odds_api.py live                          # current lines, 10 books (2 credits)
    python scripts/odds_api.py build                         # cached snapshots -> data/processed/pinnacle_lines.parquet
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from nflweather import oddsapi
from nflweather.config import RAW

ap = argparse.ArgumentParser()
ap.add_argument("cmd", choices=["plan", "backfill", "live", "build"])
ap.add_argument("--confirm", action="store_true")
ap.add_argument("--max-credits", type=int, default=9000)
ap.add_argument("--seasons", default="2024,2025")
ap.add_argument("--markets", default="totals")
a = ap.parse_args()

games = pd.read_csv(RAW / "games.csv")
seasons = tuple(int(s) for s in a.seasons.split(","))
if a.cmd in ("plan", "backfill"):
    oddsapi.backfill(games, seasons, tuple(a.markets.split(",")), confirm=a.cmd == "backfill" and a.confirm,
                     max_credits=a.max_credits)
elif a.cmd == "live":
    b = oddsapi.Budget(10)
    df = oddsapi.live(budget=b, floor=oddsapi.MANUAL_FLOOR)
    df = df[(df.market == "totals") & (df.book == oddsapi.RULE_BOOK)]
    print(df[["commence_utc", "away", "home", "total", "over_price", "under_price"]].to_string(index=False))
    print(f"credits used {b.used}, remaining {b.remaining}")
else:
    L = oddsapi.lines_table(games)
    print(f"{len(L):,} snapshot-lines across {L.game_id.nunique() if len(L) else 0} games")
