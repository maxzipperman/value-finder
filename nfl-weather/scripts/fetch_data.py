"""Pull (or refresh) every raw input. Safe to re-run: only new data is downloaded.

    python scripts/fetch_data.py            # everything
    python scripts/fetch_data.py --skip-weather
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from nflweather import fetch, odds
from nflweather.config import RAW

ap = argparse.ArgumentParser()
ap.add_argument("--skip-pbp", action="store_true")
ap.add_argument("--skip-weather", action="store_true")
ap.add_argument("--per-minute", type=float, default=75)
args = ap.parse_args()

print("schedule…", flush=True)
fetch.fetch_schedule()
games = pd.read_csv(RAW / "games.csv")

if not args.skip_pbp:
    print("play-by-play…", flush=True)
    fetch.fetch_pbp()

print("home-city climate (NOAA GHCN-D)…", flush=True)
fetch.fetch_home_climate()

print("opening/closing lines 2007-2021 (Sportsbook Reviews Online archive)…", flush=True)
odds.fetch_all()

if not args.skip_weather:
    print("forecasts for upcoming games…", flush=True)
    fetch.fetch_forecasts(games)
    print("game-time weather (Open-Meteo archive)…", flush=True)
    fetch.fetch_game_weather(games, per_minute=args.per_minute)
print("done.", flush=True)
