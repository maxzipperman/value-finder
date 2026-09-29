"""What to expect from the forward tests: Monte Carlo of a season at the pre-registered stake, and the
chance each pre-registered decision rule gives a clear answer. No new data, no API calls, and no
variants: nothing here tests a hypothesis, it only sizes the noise around the tests already running.

Inputs
  Volumes: the 2025 dress rehearsals (nfl-weather and cfb-weather scripts/rehearse_2025.py) and the
           screen's 65 Rule HT bets a season.
  Win rates: each rule's historical rate (STRATEGY.md files; strategy-research/README.md), half that
           edge, and no edge (50%, i.e. an efficient market where you pay the vig).
  CLV: Rule B is graded on CLV. The proxy is the open-to-close move in 15+ mph outdoor games
       (NFL 2007-21 SBR, CFB 2016-25 cfbfastR). Rule B enters 1-3 days out, later than the open, so the
       full proxy is optimistic; half of it and zero are shown too.

Outputs: output/simulations.csv, output/simulations.log (console)
Run from the repo root:  nfl-weather/.venv/bin/python strategy-research/simulate_decisions.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "output"
SIMS, STAKE, PAYOUT = 20_000, 0.5, 100 / 110           # stake in % of starting bankroll; win pays 0.909 at -110
BE = 110 / 210
rng = np.random.default_rng(0)
rows = []

# ---------------------------------------------------------------- 1. a season at 0.5% stakes
RULES = {  # name: (signals a season, historical win rate, source)
    "NFL Rule B (Weeks 5-18)": (17, 0.572, "57.2% of 682 observed-wind games; 17 signals in the 2025 rehearsal"),
    "CFB Rule B (Oct 1 on)": (25, 0.566, "56.6% of 990 observed-wind games; the rehearsal's 32 used a perfect forecast"),
    "CFB Rule HT (full season)": (65, 0.577, "373-273 in 2016-25, about 65 a season"),
}
for rule, (n_mean, p_hist, src) in RULES.items():
    for label, p in (("historical rate", p_hist), ("half the edge", (p_hist + 0.5) / 2), ("no edge", 0.5)):
        n = rng.poisson(n_mean, SIMS)
        pnl, dd = np.empty(SIMS), np.empty(SIMS)
        for i, k in enumerate(n):
            path = np.cumsum(np.where(rng.random(k) < p, PAYOUT, -1.0)) * STAKE
            path = np.concatenate([[0.0], path])
            pnl[i], dd[i] = path[-1], (np.maximum.accumulate(path) - path).max()
        rows.append(dict(section="season at 0.5% stakes", rule=rule, scenario=f"{label} ({100 * p:.1f}%)",
                         bets=n_mean, median_pnl_pct=np.median(pnl), p10_pnl_pct=np.percentile(pnl, 10),
                         p90_pnl_pct=np.percentile(pnl, 90), p_losing_season=(pnl < 0).mean(),
                         median_max_drawdown_pct=np.median(dd), p90_max_drawdown_pct=np.percentile(dd, 90), note=src))

# ---------------------------------------------------------------- 2. Rule HT's single decision after 2027
# 2026 Weeks 6+ (34 in the 2025 rehearsal) plus a full 2027 (65); pushes ignored.
crit = {n: next((w for w in range(n + 1) if stats.binom.sf(w - 1, n, BE) < 0.05), n + 1) for n in range(1, 300)}
for p in (0.577, 0.55, BE, 0.50):
    n = rng.poisson(34 + 65, SIMS)
    w = rng.binomial(n, p)
    promote = w >= np.array([crit[k] for k in n])
    drop = w / n <= BE
    rows.append(dict(section="Rule HT decision after 2027", rule="CFB Rule HT", scenario=f"true win rate {100 * p:.1f}%",
                     bets=99, p_promote=promote.mean(), p_keep_on_paper=(~promote & ~drop).mean(), p_drop=drop.mean(),
                     note="promote: one-sided binomial p < 0.05 vs 52.4% and ROI > 0; drop: at or below 52.4%"))

# ---------------------------------------------------------------- 3. Rule B's CLV tests
g = pd.read_parquet(ROOT / "nfl-weather/data/processed/games.parquet")
g = g[g.wx_src.isin(["gamebook", "era5"]) & (g.wx_wind >= 15) & g.total_open.notna() & g.sbr_total_close.notna()]
c = pd.read_parquet(ROOT / "cfb-weather/data/processed/games.parquet")
c = c[(c.wx_src == "station") & (c.wx_wind >= 15) & c.open_total.notna() & c.close_total.notna() & c.season.between(2016, 2025)]
CLV = {"NFL Rule B": ((g.total_open - g.sbr_total_close).to_numpy(), 17, "after Week 18 (about 17 signals)"),
       "CFB Rule B": ((c.open_total - c.close_total).to_numpy(), 40, "after 40 signals")}
for rule, (clv, n, when) in CLV.items():
    for label, shift in (("full open-to-close move", 0.0), ("half of it", -clv.mean() / 2), ("no edge", -clv.mean())):
        x = clv + shift
        pos20 = x[rng.integers(0, len(x), (SIMS, 20))].mean(axis=1) > 0
        s = x[rng.integers(0, len(x), (SIMS, n))]
        lo = s.mean(axis=1) - 1.96 * s.std(axis=1, ddof=1) / np.sqrt(n)
        rows.append(dict(section="Rule B CLV tests", rule=rule, scenario=f"{label} (mean {x.mean():+.2f} pts, sd {x.std():.2f})",
                         bets=n, p_keep=(lo > 0).mean(), p_stake_gate_after_20=pos20.mean(),
                         note=f"keep: mean CLV > 0 with the 95% CI above zero, {when}; stake gate: mean CLV > 0 "
                              f"after 20 signals; CLV proxy from {len(x)} windy games"))

res = pd.DataFrame(rows)
res.to_csv(OUT / "simulations.csv", index=False)
pd.set_option("display.width", 250, "display.max_colwidth", 80)
for sec, d in res.groupby("section", sort=False):
    print(f"\n{sec}\n" + d.dropna(axis=1, how="all").drop(columns=["section", "note"]).round(3).to_string(index=False))
