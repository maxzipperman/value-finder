"""Write the frozen pricing cohort (data/processed/pricing_cohort.json) once.

The pricing model (PREREGISTRATION.md) prices an under from the residuals of outdoor games with 15+ mph
observed wind through 2023. This script computes them from games.parquet and commits them to a file, so
a later rebuild of the games table can't move the model. It refuses to overwrite an existing file
unless --force is given, and changing the file needs a dated amendment.

    python scripts/freeze_pricing_cohort.py [--force]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from cfbweather.board import PRICING_LAST_SEASON, RULE_B_WIND
from cfbweather.config import PROC
from cfbweather.market import cohort_hash, cohort_residuals, load_games

ap = argparse.ArgumentParser()
ap.add_argument("--force", action="store_true")
args = ap.parse_args()
dest = PROC / "pricing_cohort.json"
if dest.exists() and not args.force:
    sys.exit(f"{dest} exists; it is frozen. Changing it needs a dated amendment (then rerun with --force).")
hist = load_games(2006, PRICING_LAST_SEASON)
resid = cohort_residuals(hist, (hist.outdoor == 1) & (hist.wx_wind >= RULE_B_WIND))
dest.write_text(json.dumps(dict(
    created=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
    definition=f"final total - closing total; outdoor games, observed wind >= {RULE_B_WIND} mph, seasons 2006-{PRICING_LAST_SEASON}",
    n=len(resid), sha256=cohort_hash(resid), frozen=True, residuals=[round(float(x), 4) for x in resid]), indent=0))
print(f"wrote {dest}: n={len(resid)}, sha256={cohort_hash(resid)}")
