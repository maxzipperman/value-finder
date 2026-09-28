"""Paper-log the price you actually got after an alert (issue #5). score_forward.py compares
each fill with the alert-time quote, so the ledger measures the cost of waiting.

    python scripts/log_fill.py GAME_ID --rule rule_b --line 44.5 --price -108 [--book fanduel] [--at 2026-10-11T15:05Z]

Appends to data/forward/fills.csv. Rules: rule_b.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from nflweather.config import ROOT

ap = argparse.ArgumentParser()
ap.add_argument("game_id")
ap.add_argument("--rule", required=True, choices="rule_b".split(","))
ap.add_argument("--line", type=float, required=True, help="the total you got")
ap.add_argument("--price", type=float, required=True, help="American odds you got on the under")
ap.add_argument("--book", default="")
ap.add_argument("--at", default=None, help="fill time, UTC (default: now)")
ap.add_argument("--fills", default=str(ROOT / "data" / "forward" / "fills.csv"))
a = ap.parse_args()

at = pd.Timestamp(a.at) if a.at else pd.Timestamp.now(tz="UTC")
at = at.tz_localize("UTC") if at.tzinfo is None else at.tz_convert("UTC")
row = pd.DataFrame([dict(fill_utc=at.strftime("%Y-%m-%dT%H:%M:%SZ"), game_id=a.game_id, rule=a.rule, line=a.line,
                         price=a.price, book=a.book)])
path = Path(a.fills)
path.parent.mkdir(parents=True, exist_ok=True)
row.to_csv(path, mode="a", header=not path.exists(), index=False)
print(f"logged {a.rule} {a.game_id}: under {a.line} at {a.price:+.0f} {a.book}".rstrip())
