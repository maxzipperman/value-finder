"""Paths and constants shared by the pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
OUT = ROOT / "output"
TABLES = OUT / "tables"
FIGS = OUT / "figures"

FIRST_SEASON = 1999           # first season of nflverse play-by-play
THESIS_SEASONS = (2002, 2013)  # sample used in Zipperman (2014)
HOLDOUT_SEASONS = (2014, 2025)  # out-of-sample test window

DOME_TEMP, DOME_WIND = 72.0, 0.0  # thesis convention for games without weather

USER_AGENT = "nfl-weather-research/1.0 (academic replication; contact via GitHub)"

for p in (RAW, PROC, TABLES, FIGS, RAW / "pbp", RAW / "weather"):
    p.mkdir(parents=True, exist_ok=True)
