"""Descriptive checks on the MOS replay's per-game rows (issue #40 review, Sep 29).

Reads data/processed/mos_replay{tag}.parquet, the output of scripts/mos_replay.py, and prints
the numbers the README quotes next to the result: why MOS fires more often than the observed
wind, which observed threshold matches MOS's 15 mph, the both-fired / MOS-only split with a test
of the gap between them, how many signals the observed-wind evidence already counts, how many
Open-Meteo signals are also MOS signals, and which run cycle the replay reads.

Nothing here is a rule or a variant, and nothing changes the replay: the replay's game
selection, run selection and grading are as they were when the 2006-25 download started (the
full run added descriptive tables only). The splits use the game's observed wind, which isn't
known at bet time, so they describe the result; they can't be bet.

    python scripts/mos_replay_checks.py [--seasons 2023-2025]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from scipy import stats

from cfbweather.config import OUT, PROC

WIND = 15.0
BREAK_EVEN = 110 / 210


def record(s: pd.DataFrame) -> tuple[int, int, int]:
    w, p = int(s.under_win.sum()), int(s.push.sum())
    return w, len(s) - w - p, p


def fmt(s: pd.DataFrame) -> str:
    w, l, p = record(s)
    return f"{len(s)} games, {w}-{l}-{p} ({100 * w / max(w + l, 1):.1f}%)"


def split(m: pd.DataFrame) -> dict:
    """MOS signals split by whether the observed wind also reached 15 (uses the result)."""
    sig = m[m.mos_signal]
    both, mos_only = sig[sig.obs_signal], sig[~sig.obs_signal]
    (wb, lb, _), (wm, lm, _) = record(both), record(mos_only)
    return dict(sig=sig, both=both, mos_only=mos_only,
                fisher_p=stats.fisher_exact([[wb, lb], [wm, lm]]).pvalue,
                both_vs_be_p=stats.binomtest(wb, wb + lb, BREAK_EVEN, alternative="greater").pvalue,
                mos_only_vs_be_p=stats.binomtest(wm, wm + lm, BREAK_EVEN, alternative="greater").pvalue)


def matched_threshold(mos_mph: pd.Series, obs_mph: pd.Series) -> float:
    """The observed wind reached as often as MOS reaches 15 mph, on games with both."""
    share = (mos_mph >= WIND).mean()
    return float(obs_mph.quantile(1 - share))


def checks(d: pd.DataFrame, om: pd.DataFrame | None = None) -> list[str]:
    m = d[d.has_mos]
    b1 = m[m.mos1_mph.notna() & m.wx_wind.notna()]
    l1, l2 = m.mos1_mph >= WIND, m.mos2_mph >= WIND
    n = len(m)
    out = [f"Games with a MOS forecast: {n}",
           "",
           "Why MOS fires more often than the observed wind:",
           f"  lead 1 at 15+: {int(l1.sum())} ({100 * l1.mean():.2f}%); lead 2 at 15+: {int(l2.sum())} "
           f"({100 * l2.mean():.2f}%); either lead (the rule): {int(m.mos_signal.sum())} ({100 * m.mos_signal.mean():.2f}%)",
           f"  observed at 15+: {int(m.obs_signal.sum())} ({100 * m.obs_signal.mean():.2f}%)",
           f"  signals from lead 1 alone: {int(l1.sum())}; added only by lead 2: {int((l2 & ~l1).sum())}",
           f"  observed threshold reached as often as lead-1 MOS reaches 15 (n={len(b1)}): "
           f"{matched_threshold(b1.mos1_mph, b1.wx_wind):.2f} mph",
           f"  observed threshold reached as often as either lead reaches 15 (n={int(m.wx_wind.notna().sum())}): "
           f"{float(m.wx_wind.quantile(1 - m.mos_signal.mean())):.2f} mph"]
    near = b1[(b1.mos1_mph >= 14) & (b1.mos1_mph <= 16)]
    out.append(f"  games with lead-1 MOS of 14-16 mph: n={len(near)}, mean MOS {near.mos1_mph.mean():.2f}, "
               f"mean observed {near.wx_wind.mean():.2f} mph")

    e = b1.mos1_mph - b1.wx_wind
    out += ["", f"Lead-1 MOS minus observed (n={len(b1)}): mean {e.mean():+.2f}, MAE {e.abs().mean():.2f}, "
                f"corr {b1.mos1_mph.corr(b1.wx_wind):.3f} mph"]
    for s, g in b1.groupby("season"):
        out.append(f"  {s}: n={len(g)}, mean {(g.mos1_mph - g.wx_wind).mean():+.2f} mph")

    sp = split(m)
    out += ["", "Where the wins fell (descriptive; uses the result, so not a rule):",
            f"  MOS and observed both >= 15: {fmt(sp['both'])}; vs break-even one-sided p = {sp['both_vs_be_p']:.3f} "
            "(unadjusted, and the group is picked using the observed wind)",
            f"  MOS only: {fmt(sp['mos_only'])}; vs break-even one-sided p = {sp['mos_only_vs_be_p']:.3f}",
            f"  gap between the two, Fisher exact two-sided p = {sp['fisher_p']:.3f}",
            f"  MOS signals the observed-wind evidence also counts (observed >= 15): {len(sp['both'])} of {len(sp['sig'])}"]

    if om is not None:
        mm = m.merge(om[["game_id", "fc_signal"]], on="game_id", how="inner")
        o = mm[mm.fc_signal.astype(bool)]
        ob, oo = o[o.obs_signal], o[~o.obs_signal]
        out += ["", f"Open-Meteo replay (games in both, n={len(mm)}):",
                f"  Open-Meteo signals: {len(o)}; also MOS signals: {int(o.mos_signal.sum())}",
                f"  Open-Meteo both-fired: {fmt(ob)}, of which MOS signals {int(ob.mos_signal.sum())}",
                f"  Open-Meteo forecast-only: {fmt(oo)}, of which MOS signals {int(oo.mos_signal.sum())}",
                "  Open-Meteo by season, all its games (data/processed/forecast_replay.parquet):"]
        for s, g in om[om.fc_signal.astype(bool)].groupby("season"):
            out.append(f"    {s}: {fmt(g)}")

    out += ["", "Run cycle the replay read (UTC hour of the run: games):"]
    for n_ in (1, 2, 3):
        c = m[f"mos{n_}_runtime"].dropna()
        out.append(f"  lead {n_}: {pd.to_datetime(c).dt.hour.value_counts().sort_index().to_dict()}")
    out += ["", "Variants added: 0 (these are descriptions of the one replayed rule)."]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", help="e.g. 2023-2025 (default 2006-2025)")
    args = ap.parse_args()
    a, _, b = (args.seasons or "2006-2025").partition("-")
    seasons = (int(a), int(b or a))
    tag = "" if seasons == (2006, 2025) else f"_{seasons[0]}_{seasons[1]}"
    d = pd.read_parquet(PROC / f"mos_replay{tag}.parquet")
    p = PROC / "forecast_replay.parquet"
    om = pd.read_parquet(p, columns=["game_id", "season", "fc_signal", "under_win", "push"]) if p.exists() else None
    lines = [f"MOS replay checks, {seasons[0]}-{seasons[1]} (from data/processed/mos_replay{tag}.parquet)", "",
             *checks(d, om)]
    text = "\n".join(lines)
    (OUT / f"mos_replay_checks{tag}.log").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
