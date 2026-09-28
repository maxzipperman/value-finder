"""Build processed datasets from the raw cache: python scripts/build_data.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nflweather.build import build

build()
