"""Paths and constants shared by the CFB pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
OUT = ROOT / "output"
TABLES = OUT / "tables"

FIRST_SEASON = 2006          # first season with betting totals in cfbfastR-data
USER_AGENT = "cfb-weather-research/1.0 (academic research)"

for p in (RAW, PROC, TABLES, RAW / "meteostat", RAW / "cfbfastr"):
    p.mkdir(parents=True, exist_ok=True)
