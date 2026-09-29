"""The registered keep test when closing-line moves on the same day move together: how often it keeps a rule
with no edge, with its interval computed the plain way and grouped by game day (nfl-weather amendment 7,
cfb-weather amendment 5). It changes how a test is graded, not a betting rule: 0 variants.

The simulation machinery is section 4 of simulate_decisions.py, reused as it stands: the CLV proxy (the
open-to-close moves of windy games), the dependence estimates (a realistic case and a stress case), and the
calendars that replay the dates of the windiest games of 2016-25 onto 2026. That file's sections 1 to 4b are
run here with its one write (output/simulations.csv) switched off, so none of its committed outputs is
rewritten; they draw from their own fixed seeds (0 and 51). Everything drawn here comes from --seed.

  (1) The keep test at 40 bets, no edge, half and the full historical move, for each sport, each season
      volume and each dependence case (independent, realistic, stress).
  (2) Model-free, no edge, 40 bets: paths of real centred moves chained from whole historical days (both
      sports) and whole NFL seasons in kickoff order. No correlation model at all.
  (3) The NFL's two looks (amendment 6, section 6): the 2026 horizon only with 40 in the 2026 regular season
      (Weeks 5-18 of one replayed season), otherwise once after 2027 on both seasons pooled (Weeks 5-18 of one
      replayed season, then Weeks 1-18 of another), with every CLV keep criterion: the interval, mean CLV
      positive in each half or season, at least 20 closes, and keep-and-drop-both-met is a drop. The win rate
      against the close is not simulated, so the rate is an upper bound for that criterion.

The grouped interval (the registered reading): the plain mean m of the n CLVs; the bets grouped by the Eastern
calendar date of their kickoff; G days; s_g the sum over day g's bets of (CLV - m); the variance of the mean
(G / (G - 1)) x sum(s_g^2) / n^2; the interval m +/- t x its square root, with t the 97.5th percentile of
Student's t on G - 1 degrees of freedom; no interval with fewer than 2 days. The plain interval is
m +/- 1.96 x sd / sqrt(n). A path "keeps" when m > 0 and the lower bound is above 0.

Outputs: output/keep_test_check.csv and output/keep_test_check.log (the console). Deterministic for a seed.
Run from the repo root:  nfl-weather/.venv/bin/python strategy-research/keep_test_check.py [--seed 29]
It takes about half a minute.
"""
import argparse
import contextlib
import io
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
SIM = HERE / "simulate_decisions.py"
WRITE = 'res.to_csv(OUT / "simulations.csv", index=False)'     # simulate_decisions.py's only write before 4c
CUT = "# 4c. Thresholds"                                          # sections 1 to 4b end here

ap = argparse.ArgumentParser()
ap.add_argument("--seed", type=int, default=29)
ap.add_argument("--paths", type=int, default=40_000, help="simulated paths per case")
args = ap.parse_args()

src = SIM.read_text()
if src.count(WRITE) != 1 or src.count(CUT) != 1 or src.index(WRITE) > src.index(CUT):
    sys.exit(f"{SIM.name} has changed: its only write before section 4c is no longer where this check expects it, "
             "so it isn't run (its committed outputs must not be rewritten)")
body = src[:src.index(CUT)].replace(WRITE, "pass")
if "to_csv" in body or "write_text" in body or "to_parquet" in body:
    sys.exit(f"{SIM.name} writes a file in sections 1 to 4b that this check doesn't know about; not run")
ns = {"__file__": str(SIM), "__name__": "simulate_decisions"}
t0 = time.time()
with contextlib.redirect_stdout(io.StringIO()):       # sections 1-3 print their own tables; they aren't ours
    exec(compile(body, str(SIM), "exec"), ns)
np, pd, stats = ns["np"], ns["pd"], ns["stats"]
krng = np.random.default_rng(args.seed)
ns["grng"] = krng                 # season_draws reads the module-level generator: from here on every draw is ours
N, SIMS = 40, args.paths
IND, REAL, STRESS = ns["IND"], ns["REAL"], ns["STRESS"]
LOG, rows = [], []


def say(text=""):
    print(text)
    LOG.append(str(text))


def grouped(x, day, mask=None):
    """Per path: mean, grouped-by-day lower bound (t on G - 1 df), plain lower bound, n, G. `day` holds day ids
    numbered 0..G-1 over the bets the mask keeps."""
    sims, L = x.shape
    mask = np.ones_like(x, bool) if mask is None else mask
    n = mask.sum(axis=1)
    m = (x * mask).sum(axis=1) / np.maximum(n, 1)
    r = (x - m[:, None]) * mask
    flat = (np.where(mask, day, 0) + np.arange(sims)[:, None] * L).ravel()
    s = np.bincount(flat, weights=r.ravel(), minlength=sims * L).reshape(sims, L)
    G = np.where(mask, day, -1).max(axis=1) + 1
    var = np.where(G > 1, G / np.maximum(G - 1, 1) * (s ** 2).sum(axis=1) / np.maximum(n, 1) ** 2, np.nan)
    lo_g = m - stats.t.ppf(0.975, np.maximum(G - 1, 1)) * np.sqrt(var)
    sd = np.sqrt(((x - m[:, None]) ** 2 * mask).sum(axis=1) / np.maximum(n - 1, 1))
    lo_p = m - 1.96 * sd / np.sqrt(np.maximum(n, 1))
    return m, lo_g, lo_p, n, G


say(f"Keep test check (nfl-weather amendment 7, cfb-weather amendment 5): seed {args.seed}, {SIMS:,} simulated "
    "paths per case; 0 variants")
say("Dependence used (day share, season share), from simulate_decisions.py section 4a:")
for sport, d in ns["DEP"].items():
    say(f"  {sport}: realistic {d[REAL][0]:.2f} + {d[REAL][1]:.2f}; stress {d[STRESS][0]:.2f} + {d[STRESS][1]:.2f}")

# ---------------------------------------------------------------- (1) the keep test at 40 bets
for sport, (start, _, parts, volumes) in ns["CAL"].items():
    clv = ns["PROXY"][sport][0]
    deps = [(IND, ns["DEP"][sport][IND]), (REAL, ns["DEP"][sport][REAL]), (STRESS, ns["DEP"][sport][STRESS])]
    if sport == "NFL Rule B":        # a diagnostic: the realistic day share with no season share
        deps.append(("realistic day share only (season share 0)", (ns["DEP"][sport][REAL][0], 0.0)))
    for dep, shares in deps:
        for vol in volumes:
            dr = ns["season_draws"](ns["PATS"][sport, vol][2], SIMS)
            e = clv[krng.integers(0, len(clv), (SIMS, N))] - clv.mean()
            V, W = krng.standard_normal((SIMS, N)), krng.standard_normal((SIMS, N))
            x0 = ns["noise"](sport, e, V, W, None if dep == IND else dr, shares)
            for scen, cut in ns["SCEN"]:
                m, lo_g, lo_p, n, G = grouped(x0 + (1 - cut) * clv.mean(), dr[1])
                rows.append(dict(section="keep test at 40 bets", sport=sport, case=dep, volume=vol, scenario=scen,
                                 paths=SIMS, plain=((m > 0) & (lo_p > 0)).mean(),
                                 grouped=((m > 0) & (lo_g > 0) & (G > 1)).mean(), median_days=np.median(G)))
R = pd.DataFrame(rows)
pd.set_option("display.width", 250)
say("\n(1) The keep test at 40 bets: share of paths kept, plain interval and interval grouped by game day")
say(R.pivot_table(index=["sport", "case", "volume"], columns="scenario", values=["plain", "grouped"], sort=False)
    .round(4).to_string())
say("Median game days among the 40 bets: " + "; ".join(
    f"{s} {v}: {int(d.median_days.iloc[0])}" for (s, v), d in R[R.case == REAL].groupby(["sport", "volume"], sort=False)))

# ---------------------------------------------------------------- (2) model-free: whole real days and seasons
mf = []
for sport, (clv, day, season) in ns["PROXY"].items():
    order = np.argsort(day, kind="stable")
    z, d, s = clv[order] - clv.mean(), day[order], season[order]
    kinds = {"whole days": [(z[d == v], np.zeros((d == v).sum(), int)) for v in pd.unique(d)]}
    if sport == "NFL Rule B":
        kinds["whole seasons"] = [(z[s == v], pd.factorize(d[s == v])[0]) for v in pd.unique(s)]
    for kind, blocks in kinds.items():
        x, dd = np.empty((SIMS, N)), np.empty((SIMS, N), int)
        pick = krng.integers(len(blocks), size=(SIMS, N))
        for i in range(SIMS):
            xs, ds, k, j, off = [], [], 0, 0, 0
            while k < N:
                b, bd = blocks[pick[i, j]]
                xs.append(b)
                ds.append(bd + off)
                off += bd.max() + 1
                k, j = k + len(b), j + 1
            x[i], dd[i] = np.concatenate(xs)[:N], np.concatenate(ds)[:N]
        dd = np.array([pd.factorize(r)[0] for r in dd])
        m, lo_g, lo_p, n, G = grouped(x, dd)
        mf.append(dict(section="model-free, no edge, 40 bets", sport=sport, case=f"resampled {kind}",
                       blocks=len(blocks), scenario="no edge", paths=SIMS, plain=((m > 0) & (lo_p > 0)).mean(),
                       grouped=((m > 0) & (lo_g > 0) & (G > 1)).mean()))
MF = pd.DataFrame(mf)
say("\n(2) Model-free, no edge, 40 bets: share of paths kept\n"
    + MF[["sport", "case", "blocks", "paths", "plain", "grouped"]].round(4).to_string(index=False))

# ---------------------------------------------------------------- (3) the NFL's two looks (amendment 6, section 6)
n26f, nfl = ns["n26"], ns["nfl"]
allw = n26f[(n26f.game_type == "REG") & n26f.wx_src.isin(["gamebook", "era5"]) & n26f.wx_wind.notna()
            & n26f.season.between(2016, 2025)].copy()
allw["dkey"] = allw.week * 7 + allw.weekday.map(ns["DOW"])
allw["u"] = krng.random(len(allw))
sport = "NFL Rule B"
clv = ns["PROXY"][sport][0]
two = []
for vol in ns["CAL"][sport][3]:
    ws = np.unique(nfl.wx_wind.to_numpy())                   # the same wind cut-off as the section-4 calendar
    avg = (len(nfl) - np.searchsorted(np.sort(nfl.wx_wind.to_numpy()), ws)) / nfl.season.nunique()
    i = int(np.argmax(avg <= vol))
    hi, lo = ws[i], ws[i - 1]
    q = (vol - avg[i]) / (avg[i - 1] - avg[i])
    k = allw[(allw.wx_wind >= hi) | ((allw.wx_wind == lo) & (allw.u < q))]
    seasons = sorted(k.season.unique())
    s26 = [k[(k.season == s) & (k.week >= 5)].sort_values("dkey") for s in seasons]
    s27 = [k[(k.season == s)].sort_values("dkey") for s in seasons]
    L = max(len(a) for a in s26) + max(len(b) for b in s27)
    for dep in (IND, REAL, STRESS):
        rd, rs = ns["DEP"][sport][dep]
        a_pick, b_pick = krng.integers(len(seasons), size=SIMS), krng.integers(len(seasons), size=SIMS)
        day, sea, half = np.zeros((SIMS, L), int), np.zeros((SIMS, L), int), np.zeros((SIMS, L), int)
        mask, n26 = np.zeros((SIMS, L), bool), np.zeros(SIMS, int)
        for p in range(SIMS):
            a, b = s26[a_pick[p]], s27[b_pick[p]]
            na, nb = len(a), len(b)
            dk = np.concatenate([pd.factorize(a.dkey)[0], pd.factorize(b.dkey)[0] + (na + 1)])
            day[p, :na + nb] = pd.factorize(dk)[0]
            sea[p, na:na + nb] = 1
            half[p, :na] = (a.week.to_numpy() > 11)
            mask[p, :na + nb] = True
            n26[p] = na
        e = clv[krng.integers(0, len(clv), (SIMS, L))] - clv.mean()
        V, W = krng.standard_normal((SIMS, L)), krng.standard_normal((SIMS, 2))
        sd = clv.std()
        x0 = (np.sqrt(1 - rd - rs) * e + np.sqrt(rd) * sd * np.take_along_axis(V, day, axis=1)
              + np.sqrt(rs) * sd * np.take_along_axis(W, sea, axis=1))
        for scen, cut in ns["SCEN"]:
            x = x0 + (1 - cut) * clv.mean()
            # look 1, after Week 18 of 2026: only with 40 or more in the 2026 regular season, by half
            m1_mask = mask & (sea == 0)
            m1, lo1, _, n1, G1 = grouped(x, day, m1_mask)
            hv = [((x * (m1_mask & (half == h))).sum(1) / np.maximum((m1_mask & (half == h)).sum(1), 1),
                   (m1_mask & (half == h)).sum(1)) for h in (0, 1)]
            halves_ok = (hv[0][1] > 0) & (hv[1][1] > 0) & (hv[0][0] > 0) & (hv[1][0] > 0)
            hi1 = m1 + (m1 - lo1)
            look1 = n26 >= 40
            drop1 = look1 & (G1 > 1) & ((m1 <= 0) | (hi1 < 0.25))
            keep1 = look1 & (G1 > 1) & (m1 > 0) & (lo1 > 0) & halves_ok & ~drop1
            # look 2, after the 2027 regular season, both seasons pooled, by season
            m2, lo2, lo2p, n2, G2 = grouped(x, day, mask)
            hi2, hi2p = m2 + (m2 - lo2), m2 + (m2 - lo2p)
            sv = [((x * (mask & (sea == s))).sum(1) / np.maximum((mask & (sea == s)).sum(1), 1),
                   (mask & (sea == s)).sum(1)) for s in (0, 1)]
            seasons_ok = (sv[0][1] > 0) & (sv[1][1] > 0) & (sv[0][0] > 0) & (sv[1][0] > 0)
            second = ~(keep1 | drop1) & (n2 >= 20)
            interval2 = second & (G2 > 1) & (m2 > 0) & (lo2 > 0) & ~(hi2 < 0.25)
            plain2 = second & (m2 > 0) & (lo2p > 0) & ~(hi2p < 0.25)
            two.append(dict(section="NFL two looks", sport=sport, case=dep, volume=vol, scenario=scen, paths=SIMS,
                            p_look1=look1.mean(), median_bets_pooled=np.median(n2),
                            keep_two_looks=(keep1 | (interval2 & seasons_ok)).mean(),
                            keep_interval_only=(keep1 | interval2).mean(),
                            keep_plain_interval_only=(keep1 | plain2).mean()))
TWO = pd.DataFrame(two)
say("\n(3) NFL, the two looks of amendment 6 section 6, grouped interval: share of paths kept (keep_two_looks: every "
    "CLV keep criterion; the win rate against the close is not simulated)\n"
    + TWO[["volume", "case", "scenario", "paths", "p_look1", "median_bets_pooled", "keep_two_looks",
           "keep_interval_only", "keep_plain_interval_only"]].round(4).to_string(index=False))


# ---------------------------------------------------------------- the headline numbers
def rng_(d, col):
    return f"{100 * d[col].min():.1f} to {100 * d[col].max():.1f}%"


noedge = R[R.scenario == "no edge"]
say("\nHeadline, no edge, 40 bets (range over the season volumes):")
for sport in ns["CAL"]:
    for dep in (IND, REAL, STRESS):
        d = noedge[(noedge.sport == sport) & (noedge.case == dep)]
        say(f"  {sport}, {dep}: plain {rng_(d, 'plain')}, grouped {rng_(d, 'grouped')}")
for r in MF.itertuples():
    say(f"  {r.sport}, model-free {r.case}: plain {100 * r.plain:.1f}%, grouped {100 * r.grouped:.1f}%")
for r in TWO[(TWO.scenario == "no edge")].itertuples():
    say(f"  NFL two looks, {r.volume} signals a season, {r.case}: {100 * r.keep_two_looks:.1f}% "
        f"(look 1 reached in {100 * r.p_look1:.1f}% of paths)")

OUT.mkdir(exist_ok=True)
table = pd.concat([R, MF, TWO], ignore_index=True)
for col in ("volume", "paths", "blocks"):
    table[col] = table[col].astype("Int64")
table.to_csv(OUT / "keep_test_check.csv", index=False, float_format="%.4f")
(OUT / "keep_test_check.log").write_text("\n".join(LOG) + "\n")
print(f"({time.time() - t0:.0f} seconds; wrote output/keep_test_check.csv and output/keep_test_check.log)",
      file=sys.stderr)
