"""Dress rehearsal: replay 2025 Weeks 5-18 through this season's Rule B code, ledger format and
scorer, as if it were live. It tests the plumbing and shows the workload; it is not evidence
for the rule and adds no variants.

How the replay is built (no downloads, no API calls):
* Two snapshots per outdoor game, 3 and 1 days before kickoff, each using that lead's archived
  Open-Meteo forecast (fc3_wind / fc1_wind, previous-day runs), calibrated exactly as the board does.
* Every snapshot prices at the nflverse CLOSING total and under price (no 2025 intraday lines are
  in the repo), so entry equals the close and CLV is 0 by construction. Win/loss and units are real.
* Rule B status and EV come from board.rule_b_status and the board's frozen (<= 2023) windy cohort.
* Dates move forward 53 weeks (same weekday) so the unmodified scorer's 2026 window applies:
  2025 Week 5 (Oct 2) becomes Oct 8, 2026.

Outputs: output/tables/rehearsal_2025.csv (ledger), output/rehearsal_2025.log (console)
    python scripts/rehearse_2025.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from nflweather import board
from nflweather.config import OUT, PROC, ROOT
from nflweather.market import cohort_residuals, ev_under, load_games, market_p_under

SHIFT = pd.Timedelta(weeks=53)
cal = json.loads((PROC / "calibration.json").read_text())
g = pd.read_parquet(PROC / "games.parquet")
g = g[(g.season == 2025) & (g.game_type == "REG") & g.week.between(5, 18) & g.result.notna()].copy()
g["kick"] = pd.to_datetime(g.gameday + " " + g.gametime).dt.tz_localize("America/New_York").dt.tz_convert("UTC")

hist = load_games()
frozen = hist[hist.season <= board.PRICING_LAST_SEASON]
resid = cohort_residuals(frozen, (frozen.outdoor == 1) & (frozen.wx_wind >= board.RULE_B_WIND))

rows = []
for lead, col in ((3, "fc3_wind"), (1, "fc1_wind")):
    s = g.copy()
    outdoor = s.wx_src.isin(["gamebook", "era5"]) & s[col].notna()
    s["wx_src"] = np.where(outdoor, "era5", np.where(s.wx_src.isin(["gamebook", "era5"]), "missing", "indoor"))
    s["wx_wind"] = (cal["wind_intercept"] + cal["wind_slope"] * s[col]).clip(lower=0).where(outdoor)
    s["lead_days"] = lead
    s["line_src"] = "nflverse close"
    s["mkt_total"], s["mkt_under"], s["mkt_over"] = s.total_line, s.under_odds, s.over_odds
    s["ev_under"] = ev_under(s.mkt_total, s.mkt_under, s.mkt_total, resid)
    s["rule_b"] = s.apply(board.rule_b_status, axis=1)
    s["snapshot_utc"] = s.kick - pd.Timedelta(days=lead)
    rows.append(s)
S = pd.concat(rows, ignore_index=True)

# the ledger exactly as board.save writes it, dates shifted into the 2026 scoring window
led = pd.DataFrame({
    "snapshot_utc": (S.snapshot_utc + SHIFT).dt.strftime("%Y-%m-%dT%H:%M:%SZ"), "rules_version": board.RULES_VERSION,
    "game_id": S.game_id, "gameday": (pd.to_datetime(S.gameday) + SHIFT).dt.strftime("%Y-%m-%d"),
    "gametime": S.gametime, "away_team": S.away_team, "home_team": S.home_team, "lead_days": S.lead_days,
    "wx_src": S.wx_src, "wx_wind": S.wx_wind.round(1), "wx_temp": np.nan, "wx_precip": np.nan, "wx_snow": np.nan,
    "line_src": S.line_src, "total_line": S.mkt_total, "under_odds": S.mkt_under, "over_odds": S.mkt_over,
    "p_under": np.nan, "p_market": market_p_under(S.mkt_under, S.mkt_over, "shin"), "lean": "",
    "ev_under": S.ev_under, "rule_b": S.rule_b, "best_under": np.nan, "best_under_book": ""})
games = g.assign(gameday=(pd.to_datetime(g.gameday) + SHIFT).dt.strftime("%Y-%m-%d"))[
    ["game_id", "total", "total_line", "gameday", "gametime", "result"]]

with tempfile.TemporaryDirectory() as tmp:
    led.to_csv(Path(tmp) / "ledger.csv", index=False)
    games.to_csv(Path(tmp) / "games.csv", index=False)
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "score_forward.py"), "--ledger",
                          str(Path(tmp) / "ledger.csv"), "--games", str(Path(tmp) / "games.csv")],
                         capture_output=True, text=True, check=True).stdout

(OUT / "tables").mkdir(parents=True, exist_ok=True)
led.to_csv(OUT / "tables" / "rehearsal_2025.csv", index=False)
order = {"SIGNAL": 0, "negative_ev": 1, "price_too_high": 2, "no_price": 3, "outside_horizon": 4}
best = S[S.rule_b.isin(order)].assign(o=lambda d: d.rule_b.map(order)).sort_values("o").drop_duplicates("game_id")
wk = pd.DataFrame({"games": g.groupby("week").size(),
                   "rule_b_signals": best[best.rule_b == "SIGNAL"].groupby("week").size(),
                   "blocked_by_price_or_ev": best[best.rule_b != "SIGNAL"].groupby("week").size()}).fillna(0).astype(int)
print("NFL dress rehearsal: 2025 Weeks 5-18 through this season's Rule B code and scorer")
print(f"  {len(g)} games; {len(led)} ledger rows (2 per game); snapshot statuses: {S.rule_b.value_counts().to_dict()}")
print(f"  games with a wind trigger: {len(best)}; signalled: {int((best.rule_b == 'SIGNAL').sum())}; "
      f"blocked at every snapshot: {best[best.rule_b != 'SIGNAL'].rule_b.value_counts().to_dict()}")
print("\nPer week (2025 week numbers):\n" + wk.T.to_string())
print("\nScorer output (entry = close here, so CLV is 0 by construction):\n" + out)
