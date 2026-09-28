"""Weekly weather board for upcoming games (see nflweather/board.py), written to
output/this_week.csv and appended to the forward-test ledger.

    python scripts/this_week.py              # next 8 days, nflverse lines
    python scripts/this_week.py --pinnacle   # use live Pinnacle totals (1 Odds API credit; skipped when
                                             # fewer than oddsapi.MANUAL_FLOOR credits are left this month)

Anything more than ~2 days out is provisional: wind is the least reliable part
of a forecast, and the historical edge is modest.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from nflweather import board, oddsapi

ap = argparse.ArgumentParser()
ap.add_argument("--days", type=int, default=8)
ap.add_argument("--no-fetch", action="store_true")
ap.add_argument("--pinnacle", action="store_true")
args = ap.parse_args()

up = board.compute(days=args.days, refresh=not args.no_fetch, pinnacle=args.pinnacle, credit_floor=oddsapi.MANUAL_FLOOR)
if up.empty:
    sys.exit("no games in the next %d days" % args.days)

board.save(up)

pd.set_option("display.width", 250)
show = up.assign(matchup=up.away_team + " @ " + up.home_team, kick=up.gameday.str.slice(5) + " " + up.gametime,
                 total=up.mkt_total.map(lambda v: "–" if pd.isna(v) else f"{v:.1f}"),
                 pts_effect=up.pts_effect.map(lambda v: f"{v:+.1f}"), mkt_adjust=up.mkt_adjust.map(lambda v: f"{v:+.1f}"),
                 p_under=(100 * up.p_under).map(lambda v: f"{v:.0f}%"),
                 edge=(100 * up.edge).map(lambda v: "" if pd.isna(v) else f"{v:+.0f}"))
print(show[["kick", "matchup", "lead_days", "conditions", "line_src", "total", "pts_effect", "mkt_adjust", "p_under",
            "edge", "lean"]].to_string(index=False))
print("\npts_effect: historical change in combined points for this weather. mkt_adjust: how much closing totals "
      "usually move for it. edge: model P(under) minus the de-vigged market price, in points. Leans need 55%.")
