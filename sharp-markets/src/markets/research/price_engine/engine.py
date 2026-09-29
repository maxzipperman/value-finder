"""Fair prices, flags, entries, closes and grading. Every threshold here is fixed before F1 exists
(strategy-research/price-engine-preregistration-draft.md); changing one is a dated amendment, not an edit.

Fair price at each snapshot (per game and market):
  pinnacle  Pinnacle's Shin no-vig probability for its own line (primary).
  blend     Pinnacle, LowVig and BetOnline, each Shin-de-vigged, where they quote Pinnacle's line, averaged with
            config/backtest.yaml's weights (0.55 / 0.30 / 0.15) renormalized over the books present; the same
            arithmetic as markets.devig.blend. Needs Pinnacle's line, like the primary version.
A retail book's quote is compared with the fair price at the same snapshot:
  h2h       always; spreads only at Pinnacle's own spread (primary analysis); totals at any total, a different
            total converted by the registered model (model.under_at).
Flags:
  H1  expected value against the fair price >= 1%, 2% (primary) or 3%.
  H2  (issue 53, soft-book lag) a retail total at least 1 point on the good side of Pinnacle's total at the same
      snapshot, at -115 or better.
Entry: one bet per game, market and side: the first snapshot where the side is flagged, at the flagged book with
the best expected value (H2: the biggest gap, then the best price). The snapshot must be more than 60 minutes
before kickoff, so it is never the close it is graded against (and never at or after kickoff).
Grading: CLV at the price taken against Pinnacle's close and against the entry book's own close, in cents of
no-vig probability (100 * (p_close - 1/price)) and, for spreads and totals, in points; and the realized result.
A close is a book's quote in its last snapshot before kickoff, and only if that snapshot is within 60 minutes of
kickoff (F1's close is 5 to 10 minutes before).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ...sport import load_backtest_config
from .model import CFB, LABEL, NFL, SPORTS, ev, shin, under_at
from .quotes import RETAIL, SHARP

THRESHOLDS = (0.01, 0.02, 0.03)
PRIMARY_THRESHOLD = 0.02
FAIRS = ("pinnacle", "blend")
H1_MARKETS = ("totals", "spreads", "h2h")
LAG_POINTS = 1.0
LAG_MIN_DEC = 1 + 100 / 115            # -115 American
CLOSE_WINDOW = pd.Timedelta(minutes=60)
EV_ERROR = 0.10                        # EV at or above this: the prices a book is most likely to void as errors
PRIOR_COUNT = 200                      # the repo's running variant count before this pre-registration
MIN_BETS, MIN_SEASON_BETS = 100, 20
EPS = 1e-9


@dataclass(frozen=True)
class Variant:
    hyp: str            # H1 (price engine) or H2 (soft-book lag)
    sport: str
    market: str
    fair: str           # pinnacle | blend | lag
    threshold: float    # H1: minimum EV; H2: minimum gap in points

    @property
    def id(self) -> str:
        t = f"ev{self.threshold:.0%}" if self.hyp == "H1" else f"gap{self.threshold:g}"
        return f"{self.hyp}-{LABEL[self.sport]}-{self.market}-{self.fair}-{t}"

    @property
    def primary(self) -> bool:
        return self.hyp == "H2" or (self.fair == "pinnacle" and self.threshold == PRIMARY_THRESHOLD)


VARIANTS = tuple([Variant("H1", s, m, f, t) for s in SPORTS for m in H1_MARKETS for f in FAIRS for t in THRESHOLDS]
                 + [Variant("H2", s, "totals", "lag", LAG_POINTS) for s in SPORTS])
RUNNING_COUNT = PRIOR_COUNT + len(VARIANTS)
ALPHA = 0.05 / RUNNING_COUNT


# ---------------------------------------------------------------- fair prices
def blend_weights() -> dict[str, float]:
    return dict(load_backtest_config()["fair"]["blend_weights"])


def _same_line(a: pd.Series, b: pd.Series) -> np.ndarray:
    a, b = a.to_numpy(float), b.to_numpy(float)
    return (np.isnan(a) & np.isnan(b)) | np.isclose(a, b)


def fair_table(q: pd.DataFrame, weights: dict[str, float] | None = None) -> pd.DataFrame:
    """Per (sport, event_id, snap, market): Pinnacle's line, its fair P(side a), its last_update, and the blend's
    fair P(side a) at Pinnacle's line."""
    weights = weights or blend_weights()
    key = ["sport", "event_id", "snap", "market"]
    sharp = q[q.book.isin(SHARP)].copy()
    sharp["q"] = np.nan
    for s in SPORTS:
        m = (sharp.sport == s).to_numpy()
        if m.any():
            sharp.loc[m, "q"] = shin(sharp.dec_a[m], sharp.dec_b[m], s)
    pin = sharp[sharp.book == "pinnacle"][key + ["line", "q", "upd"]].rename(
        columns={"line": "pin_line", "q": "pin_q", "upd": "pin_upd"})
    both = sharp.merge(pin[key + ["pin_line"]], on=key)
    both = both[_same_line(both.line, both.pin_line)].copy()
    both["w"] = both.book.map(weights).fillna(0.0)
    both = both[(both.w > 0) & both.q.notna()]            # a book whose prices can't be de-vigged carries no weight
    both["wq"] = both.w * both.q
    agg = both.groupby(key).agg(wq=("wq", "sum"), w=("w", "sum"), n_sharp=("book", "nunique")).reset_index()
    agg["blend_q"] = agg.wq / agg.w
    return pin.merge(agg[key + ["blend_q", "n_sharp"]], on=key, how="left")


def side_rows(q: pd.DataFrame, fair: pd.DataFrame) -> pd.DataFrame:
    """Every retail quote as two rows, one per side, with the fair probability and EV of that side under both
    fair versions. `line` stays the market's own line (the home spread, the total)."""
    key = ["sport", "event_id", "snap", "market"]
    r = q[q.book.isin(RETAIL)].drop(columns=["home", "away"]).merge(fair.drop(columns="n_sharp"), on=key, how="inner")
    parts = []
    for side_i, dec_col in ((0, "dec_a"), (1, "dec_b")):
        s = r.copy()
        s["side"] = np.where(s.market == "totals", ("over", "under")[side_i], ("home", "away")[side_i])
        s["dec"] = s[dec_col]
        parts.append(s)
    s = pd.concat(parts, ignore_index=True)
    for f in FAIRS:
        qa = s["pin_q" if f == "pinnacle" else "blend_q"].to_numpy(float)
        p = np.full(len(s), np.nan)
        is_a = s.side.isin(["home", "over"]).to_numpy()
        same = _same_line(s.line, s.pin_line)
        lined = (s.market != "h2h").to_numpy()
        # h2h, and spreads and totals at Pinnacle's line
        direct = ~lined | same
        p[direct] = np.where(is_a, qa, 1 - qa)[direct]
        # totals at another line: the registered conversion
        for sp in SPORTS:
            m = ((s.market == "totals").to_numpy() & ~same & (s.sport == sp).to_numpy())
            if m.any():
                pu = under_at(1 - qa[m], s.pin_line.to_numpy(float)[m], s.line.to_numpy(float)[m], sp)
                p[m] = np.where(is_a[m], 1 - pu, pu)
        s[f"p_{f}"] = p
        s[f"ev_{f}"] = ev(p, s.dec)
    return s.drop(columns=["dec_a", "dec_b"])


def comparable(q: pd.DataFrame, fair: pd.DataFrame) -> dict[str, int]:
    """How many retail quotes the primary analysis can compare with a fair price, and why the rest can't be."""
    key = ["sport", "event_id", "snap", "market"]
    r = q[q.book.isin(RETAIL)].merge(fair[key + ["pin_line"]], on=key, how="left", indicator=True)
    no_pin = (r._merge == "left_only").to_numpy()
    same = _same_line(r.line, r.pin_line)
    other_spread = ~no_pin & (r.market == "spreads").to_numpy() & ~same
    other_total = ~no_pin & (r.market == "totals").to_numpy() & ~same
    return {"all retail quotes": len(r),
            "no Pinnacle quote at that snapshot (not compared)": int(no_pin.sum()),
            "spread at a line other than Pinnacle's (not compared)": int(other_spread.sum()),
            "total at a line other than Pinnacle's (compared through the registered model)": int(other_total.sum()),
            "quotes from books neither sharp nor retail (ignored)": int((~q.book.isin(RETAIL + SHARP)).sum())}


# ---------------------------------------------------------------- flags and entries
def entries(sides: pd.DataFrame, v: Variant) -> pd.DataFrame:
    """The bets a variant takes: the first flagged snapshot per game, market and side. Only snapshots more than
    CLOSE_WINDOW before kickoff can be entries: the close is what a bet is graded against, and a flag first seen at
    the close would have a CLV equal to its own EV by construction."""
    s = sides[(sides.sport == v.sport) & (sides.market == v.market) & (sides.kickoff - sides.snap > CLOSE_WINDOW)]
    if v.hyp == "H1":
        f = s[s[f"ev_{v.fair}"] >= v.threshold - EPS].copy()
        f["rank"] = -f[f"ev_{v.fair}"]
        f["gap"] = np.nan
    else:
        gap = np.where(s.side == "under", s.line - s.pin_line, s.pin_line - s.line)
        f = s.assign(gap=gap)
        f = f[(f.gap >= v.threshold - EPS) & (f.dec >= LAG_MIN_DEC - EPS)].copy()
        f["rank"] = -(f.gap * 1000 + f.dec)
    f = f.sort_values(["event_id", "side", "snap", "rank", "book"])
    f = f.drop_duplicates(["sport", "event_id", "market", "side"], keep="first")
    f["ev_entry"] = f[f"ev_{v.fair}"] if v.hyp == "H1" else f["ev_pinnacle"]
    return f.drop(columns="rank").reset_index(drop=True)


# ---------------------------------------------------------------- closes and grading
def closes(q: pd.DataFrame) -> pd.DataFrame:
    """Each book's close per game and market: its last pre-kickoff quote, if within CLOSE_WINDOW of kickoff."""
    last = q.sort_values("snap").drop_duplicates(["sport", "event_id", "book", "market"], keep="last")
    last = last[last.kickoff - last.snap <= CLOSE_WINDOW]
    return last[["sport", "event_id", "book", "market", "line", "dec_a", "dec_b", "snap"]].rename(
        columns={"line": "c_line", "dec_a": "c_a", "dec_b": "c_b", "snap": "c_snap"})


def close_prob(e: pd.DataFrame, c_line, c_a, c_b) -> np.ndarray:
    """No-vig probability of each bet's side at its entry line, from a close (line, prices). Spreads: only when
    the close is at the entry line. Totals at another line: the registered conversion."""
    c_line, c_a, c_b = (np.asarray(x, float) for x in (c_line, c_a, c_b))
    out = np.full(len(e), np.nan)
    is_a = e.side.isin(["home", "over"]).to_numpy()
    line = e.line.to_numpy(float)
    for sp in SPORTS:
        m = (e.sport == sp).to_numpy()
        if not m.any():
            continue
        qa = shin(c_a[m], c_b[m], sp)
        mk = e.market.to_numpy()[m]
        same = (np.isnan(line[m]) & np.isnan(c_line[m])) | np.isclose(line[m], c_line[m])
        p = np.where(is_a[m], qa, 1 - qa)
        p = np.where((mk == "spreads") & ~same, np.nan, p)
        tot = (mk == "totals") & ~same
        if tot.any():
            pu = under_at(1 - qa[tot], c_line[m][tot], line[m][tot], sp)
            p[tot] = np.where(is_a[m][tot], 1 - pu, pu)
        out[m] = p
    return out


def clv_points(e: pd.DataFrame, c_line) -> np.ndarray:
    """Line value in points, positive when the close moved toward the bet. NaN for h2h."""
    c_line, line = np.asarray(c_line, float), e.line.to_numpy(float)
    side = e.side.to_numpy()
    pts = np.select([side == "home", side == "away", side == "under", side == "over"],
                    [line - c_line, c_line - line, line - c_line, c_line - line], np.nan)
    return np.where(e.market.to_numpy() == "h2h", np.nan, pts)


def result(e: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """(won, pushed) per bet from the final score; NaN where the game has no matched score."""
    hs, as_ = e.home_score.to_numpy(float), e.away_score.to_numpy(float)
    line, side, mk = e.line.to_numpy(float), e.side.to_numpy(), e.market.to_numpy()
    margin = np.select([mk == "h2h", mk == "spreads", mk == "totals"],
                       [hs - as_, hs + line - as_, (hs + as_) - line], np.nan)
    signed = np.where(np.isin(side, ["home", "over"]), margin, -margin)
    known = ~np.isnan(signed)
    won = np.where(known, (signed > 0).astype(float), np.nan)
    push = np.where(known, (signed == 0).astype(float), np.nan)
    return won, push


def grade(e: pd.DataFrame, cl: pd.DataFrame, scores: pd.DataFrame) -> pd.DataFrame:
    if e.empty:
        return e.assign(**{c: pd.Series(dtype=float) for c in GRADE_COLS})
    pin = cl[cl.book == "pinnacle"].drop(columns="book").add_prefix("pin_").rename(
        columns={"pin_sport": "sport", "pin_event_id": "event_id", "pin_market": "market"})
    g = e.merge(pin, on=["sport", "event_id", "market"], how="left")
    g = g.merge(cl.add_prefix("own_").rename(columns={"own_sport": "sport", "own_event_id": "event_id",
                                                      "own_book": "book", "own_market": "market"}),
                on=["sport", "event_id", "book", "market"], how="left")
    g = g.merge(scores, on=["sport", "event_id"], how="left")
    for who in ("pin", "own"):
        p = close_prob(g, g[f"{who}_c_line"], g[f"{who}_c_a"], g[f"{who}_c_b"])
        g[f"clv_{who}_cents"] = 100 * (p - 1 / g.dec.to_numpy(float))
        g[f"clv_{who}_pts"] = clv_points(g, g[f"{who}_c_line"])
    won, push = result(g)
    g["won"], g["push"] = won, push
    g["profit"] = np.where(push == 1, np.nan, np.where(won == 1, g.dec - 1, np.where(np.isnan(won), np.nan, -1.0)))
    g["pin_stale"] = ~(g.pin_upd >= g.upd)          # Pinnacle's market older than the book's (or either unknown)
    g["hours_before"] = (g.kickoff - g.snap) / pd.Timedelta(hours=1)
    return g


GRADE_COLS = ["clv_pin_cents", "clv_own_cents", "clv_pin_pts", "clv_own_pts", "won", "push", "profit", "pin_stale",
              "hours_before", "home_score", "away_score"]


# ---------------------------------------------------------------- statistics
def cmean(x, groups) -> tuple[float, float, int, float]:
    """Mean, game-clustered standard error, n, and the one-sided p-value for mean > 0."""
    x = np.asarray(x, float)
    g = np.asarray(groups)
    m = ~np.isnan(x)
    x, g = x[m], g[m]
    n = len(x)
    if n == 0:
        return math.nan, math.nan, 0, math.nan
    mean = float(x.mean())
    dev = pd.Series(x - mean).groupby(g).sum().to_numpy()
    k = len(dev)
    if k < 2:
        return mean, math.nan, n, math.nan
    se = math.sqrt(float((dev ** 2).sum()) * k / (k - 1)) / n
    p = 0.5 * math.erfc(mean / se / math.sqrt(2)) if se > 0 else math.nan
    return mean, se, n, p


def _mean(x) -> float:
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    return float(x.mean()) if len(x) else math.nan


def summarize(v: Variant, g: pd.DataFrame) -> dict:
    """One results-table row for a variant."""
    row = {"variant": v.id, "hypothesis": v.hyp, "sport": LABEL[v.sport], "market": v.market, "fair": v.fair,
           "threshold": v.threshold, "primary": v.primary, "bets": len(g),
           "games": g.event_id.nunique() if len(g) else 0}
    c = g.get("clv_pin_cents", pd.Series(dtype=float))
    mean, se, n, p = cmean(c, g.event_id) if len(g) else (math.nan, math.nan, 0, math.nan)
    row.update(ev_entry_pct=100 * _mean(g.get("ev_entry", [])), clv_pin_cents=mean, clv_pin_se=se, clv_pin_n=n,
               clv_pin_p=p)
    row.update(clv_own_cents=_mean(g.get("clv_own_cents", [])),
               clv_own_n=int(g.clv_own_cents.notna().sum()) if len(g) else 0,
               clv_pin_pts=_mean(g.get("clv_pin_pts", [])), clv_own_pts=_mean(g.get("clv_own_pts", [])),
               gap_pts=_mean(g.get("gap", [])),
               hours_before_median=float(g.hours_before.median()) if len(g) else math.nan)
    # robustness: seasons, the busiest book, stale Pinnacle, likely-void errors
    seasons = g.groupby("season").clv_pin_cents.agg(["mean", "count"]) if len(g) else pd.DataFrame()
    counted = seasons[seasons["count"] >= MIN_SEASON_BETS] if len(seasons) else seasons
    row["seasons_counted"] = len(counted)
    row["seasons_positive"] = int((counted["mean"] > 0).sum()) if len(counted) else 0
    best = seasons["mean"].idxmax() if len(seasons) and seasons["mean"].notna().any() else None
    row["clv_pin_wo_best_season"] = _mean(c[g.season != best]) if best is not None else math.nan
    top = g.book.value_counts() if len(g) else pd.Series(dtype=int)
    row["top_book"] = top.index[0] if len(top) else ""
    row["top_book_share"] = float(top.iloc[0] / len(g)) if len(top) else math.nan
    row["clv_pin_wo_top_book"] = _mean(c[g.book != row["top_book"]]) if len(top) else math.nan
    row["clv_pin_fresh_pin"] = _mean(c[~g.pin_stale.astype(bool)]) if len(g) else math.nan
    row["bets_ev_10plus"] = int((g.ev_entry >= EV_ERROR).sum()) if len(g) else 0
    row["clv_pin_ev_below_10"] = _mean(c[g.ev_entry < EV_ERROR]) if len(g) else math.nan
    # the realized result at the price taken (flat 1 unit; pushes return the stake and are left out)
    pr = g.get("profit", pd.Series(dtype=float))
    rmean, rse, rn, _ = cmean(pr, g.event_id) if len(g) else (math.nan, math.nan, 0, math.nan)
    row.update(graded=rn, pushes=int((g.get("push", pd.Series(dtype=float)) == 1).sum()),
               win_rate=_mean(g.won[g.push == 0]) if len(g) else math.nan, roi=rmean,
               roi_lo=rmean - 1.96 * rse if rn > 1 else math.nan, roi_hi=rmean + 1.96 * rse if rn > 1 else math.nan)
    return row


def decide(row: dict, blend_clv: float | None = None) -> str:
    """The draft decision rule for a primary cell (price-engine-preregistration-draft.md, "Decision rules")."""
    if not row["primary"]:
        return "reported"
    if row["bets"] < MIN_BETS or row["clv_pin_n"] < MIN_BETS:
        return "too few bets"
    kill = []
    if not row["clv_pin_cents"] > 0:
        kill.append("CLV at or below zero")
    if row["roi_hi"] < 0:
        kill.append("realized ROI significantly negative")
    if not row["clv_pin_wo_top_book"] > 0:
        kill.append("one book carries it")
    if not row["clv_pin_wo_best_season"] > 0:
        kill.append("one season carries it")
    if kill:
        return "kill: " + "; ".join(kill)
    act = [row["clv_pin_p"] < ALPHA,
           row["seasons_counted"] >= 3 and row["seasons_positive"] >= row["seasons_counted"] - 1,
           row["clv_pin_fresh_pin"] > 0, row["clv_pin_ev_below_10"] > 0,
           row["hypothesis"] == "H2" or (blend_clv is not None and blend_clv > 0)]
    return "act: paper forward test" if all(act) else "inconclusive"


def results_table(graded: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = [summarize(v, graded[v.id]) for v in VARIANTS]
    by = {r["variant"]: r for r in rows}
    for v, r in zip(VARIANTS, rows):
        blend = None
        if v.hyp == "H1":
            blend = by[Variant("H1", v.sport, v.market, "blend", v.threshold).id]["clv_pin_cents"]
        r["decision"] = decide(r, blend)
    return pd.DataFrame(rows)


def by_book(graded: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Primary cells split by the entry book (issue 53: which books lag most)."""
    out = []
    for v in VARIANTS:
        g = graded[v.id]
        if not v.primary or g.empty:
            continue
        for book, b in g.groupby("book"):
            out.append({"variant": v.id, "book": book, "bets": len(b), "clv_pin_cents": _mean(b.clv_pin_cents),
                        "clv_own_cents": _mean(b.clv_own_cents), "clv_pin_pts": _mean(b.clv_pin_pts),
                        "clv_own_pts": _mean(b.clv_own_pts), "roi": _mean(b.profit)})
    return pd.DataFrame(out, columns=["variant", "book", "bets", "clv_pin_cents", "clv_own_cents", "clv_pin_pts",
                                      "clv_own_pts", "roi"])


def lag_frequency(q: pd.DataFrame) -> pd.DataFrame:
    """Issue 53, descriptive: how often each retail book's total sits a point or more off Pinnacle's at the same
    snapshot, and how often that gap is still there at the book's next snapshot of the same game."""
    key = ["sport", "event_id", "snap"]
    t = q[q.market == "totals"]
    pin = t[t.book == "pinnacle"][key + ["line"]].rename(columns={"line": "pin_line"})
    r = t[t.book.isin(RETAIL)].merge(pin, on=key).sort_values("snap")
    r["off"] = (r.line - r.pin_line).abs() >= LAG_POINTS - EPS
    r["next_off"] = r.groupby(["sport", "event_id", "book"]).off.shift(-1)
    out = []
    for (sp, book), b in r.groupby(["sport", "book"]):
        nxt = b[b.off].next_off.dropna().astype(float)
        out.append({"sport": LABEL[sp], "book": book, "quotes": len(b), "share_1pt_off": float(b.off.mean()),
                    "still_off_next_snapshot": float(nxt.mean()) if len(nxt) else math.nan})
    return pd.DataFrame(out, columns=["sport", "book", "quotes", "share_1pt_off", "still_off_next_snapshot"])


def calibration(q: pd.DataFrame, cl: pd.DataFrame, scores: pd.DataFrame) -> pd.DataFrame:
    """Descriptive, no decision: how Pinnacle's no-vig close matched results on every game it priced. Side a is
    home (h2h, spreads) or over (totals); pushes are left out."""
    pin = cl[cl.book == "pinnacle"].merge(scores, on=["sport", "event_id"])
    out = []
    for (sp, mk), g in pin.groupby(["sport", "market"]):
        e = g.rename(columns={"c_line": "line"}).assign(side=np.where(mk == "totals", "over", "home"))
        won, push = result(e)
        p = shin(g.c_a, g.c_b, sp)
        m = (push == 0) & ~np.isnan(p)
        if not m.any():
            continue
        d = won[m] - p[m]
        out.append({"sport": LABEL[sp], "market": mk, "games": int(m.sum()), "predicted_side_a": float(p[m].mean()),
                    "actual_side_a": float(won[m].mean()), "excess": float(d.mean()),
                    "excess_se": float(d.std(ddof=1) / math.sqrt(m.sum())) if m.sum() > 1 else math.nan})
    return pd.DataFrame(out, columns=["sport", "market", "games", "predicted_side_a", "actual_side_a", "excess",
                                      "excess_se"])


__all__ = ["VARIANTS", "RUNNING_COUNT", "ALPHA", "Variant", "fair_table", "side_rows", "entries", "closes", "grade",
           "results_table", "by_book", "lag_frequency", "calibration", "NFL", "CFB"]
