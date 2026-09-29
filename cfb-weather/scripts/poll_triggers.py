"""CFB wind-trigger price poller: while a Rule B wind trigger is active, log every book's total and
prices every 10 minutes (launchd com.valuefinder.triggerpoll, ops/install_live_uses.sh). Logging
only. See cfbweather/live.py.

Costs 1 credit per run with an active trigger and nothing otherwise. A background logger: it runs
only on a paid plan and stops at the background floor (quota.py).

    python scripts/poll_triggers.py [--now 2026-10-10T18:00:00Z]

--now is a dry run: it lists the games that would be polled then, and calls and writes nothing.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("ODDS_QUOTA_KIND", "background")

import pandas as pd

from cfbweather import board, live
from cfbweather.config import ROOT

FWD = ROOT / "data" / "forward"
LEDGER, OUT = FWD / "ledger.csv", FWD / "trigger_polls.csv"

ap = argparse.ArgumentParser()
ap.add_argument("--now", help="pretend it's this UTC time when picking games (testing; a dry run)")
args = ap.parse_args()
now = pd.Timestamp(args.now) if args.now else pd.Timestamp.now(tz="UTC")

if not LEDGER.exists():
    sys.exit()
active = live.active_triggers(pd.read_csv(LEDGER), now)
if active.empty:
    sys.exit()
if args.now:
    sys.exit(print(f"{now:%Y-%m-%d %H:%M}Z trigger poll (dry run): would poll {len(active)} triggered games: "
                   + ", ".join(map(str, active.game_id))))
quotes = live.live_totals(board.odds_team_names())
if isinstance(quotes, str):
    sys.exit(print(f"{now:%Y-%m-%d %H:%M}Z trigger poll: no prices for {len(active)} triggered games ({quotes})"))
rows = live.trigger_rows(active, quotes, pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"))
FWD.mkdir(parents=True, exist_ok=True)
rows.to_csv(OUT, mode="a", header=not OUT.exists(), index=False)
print(f"{now:%Y-%m-%d %H:%M}Z trigger poll: {rows.game_id.nunique()}/{len(active)} triggered games priced, "
      f"{len(rows)} book quotes")
