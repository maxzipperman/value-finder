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

Section 4 (issue #51) compares candidate paper-to-money gates for Rule B: which test of the settled
signals' CLV should decide when real money goes in. Every gate is run
  * under no edge, half the historical open-to-close move and the full move;
  * with 0%, 20% and 40% of signals carrying a CLV of exactly 0 (the CFB primary close can be the entry
    row itself);
  * with signals independent, and with signals on the same day sharing part of their CLV, as the
    historical moves did (the correlation is measured here);
  * on the calendar, by replaying the dates of the windiest games of the last ten seasons;
and betting from the first signal is priced in units. It tests a staking rule, not a betting rule:
0 variants.

Outputs: output/simulations.csv and the console (sections 1-3; the console is saved as
         output/simulations.log), output/money_gate.csv and output/money_gate.log (section 4)
Run from the repo root:  nfl-weather/.venv/bin/python strategy-research/simulate_decisions.py
"""
import itertools
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

# ---------------------------------------------------------------- 4. The paper-to-money gate (issue #51)
# "Paper until 20 settled signals show positive average CLV" passes about half the time with no edge
# (section 3). This compares candidate gates on the same CLV proxy. It has its own random stream, so
# sections 1-3 reproduce exactly.
grng = np.random.default_rng(51)
GSIMS, BOOT, CALSIMS = 40_000, 2_000, 100_000
LOOK0, NMAX = 10, 40                  # sequential gates look after every settled signal, the 10th to the 40th
LOOKS = np.arange(LOOK0, NMAX + 1)
FLOORS, ZERO_SHARES, ALPHAS = (0.0, 0.25, 0.5), (0.0, 0.2, 0.4), (0.05, 0.10)
T_CRIT, KEEP_T = 1.65, 1.96           # the issue's one-sided t gate; the registered keep test (95% CI above 0)
SCEN = (("no edge", 1.0), ("half the move", 0.5), ("full move", 0.0))   # share of the historical mean removed
SHAPES = {"constant": np.ones(len(LOOKS)), "OBF": np.sqrt(NMAX / LOOKS)}  # boundary on t: c times this
IND, COR, STRESS = "independent", "same-day correlated", "stress: stronger correlation"
LOG = []


def say(text=""):
    print(text)
    LOG.append(str(text))


def local_day(s):
    return s.dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()


def running(x):
    """Mean and one-sided t statistic (sd with ddof 1) after each signal. A zero-variance prefix gives nan."""
    k = np.arange(1, x.shape[1] + 1)
    mean = np.cumsum(x, axis=1) / k
    var = (np.cumsum(x * x, axis=1) - k * mean ** 2) / np.maximum(k - 1, 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(var > 1e-9, mean / np.sqrt(np.abs(var) / k), np.nan)
    return mean, t


def floor_ok(m, floor):
    """Today's gate asks for a positive mean; a floor of 0.25 or 0.5 asks for at least that."""
    return m > 0 if floor == 0 else m >= floor - 1e-9


def boot_lower(x, qs):
    """One-sided percentile-bootstrap lower bounds of the mean, BOOT resamples per path."""
    sims, n = x.shape
    out = np.empty((len(qs), sims))
    for a in range(0, sims, 1000):
        w = grng.multinomial(n, np.full(n, 1 / n), size=BOOT).T / n      # n x BOOT resampling weights
        out[:, a:a + 1000] = np.quantile(x[a:a + 1000] @ w, qs, axis=1)
    return out


def icc(y, key):
    """One-way ANOVA intraclass correlation of y within groups of key."""
    k = pd.factorize(key)[0]
    K, N = k.max() + 1, len(y)
    n_i = np.bincount(k, minlength=K)
    m_i = np.bincount(k, y, K) / n_i
    msb = (n_i * (m_i - y.mean()) ** 2).sum() / (K - 1)
    msw = ((y - m_i[k]) ** 2).sum() / (N - K)
    n0 = (N - (n_i ** 2).sum() / N) / (K - 1)
    return (msb - msw) / (msb + (n0 - 1) * msw)


# 4a. How much the historical moves of windy games on the same day move together: the estimate, a permutation
#     p-value and a 95% interval from resampling whole days. Both sports are simulated at CFB's estimate
#     (NFL's own is near zero but too noisy to rule it out) and stress-tested at CFB's upper bound.
PROXY = {"CFB Rule B": (CLV["CFB Rule B"][0], local_day(c.start_utc).to_numpy()),
         "NFL Rule B": (CLV["NFL Rule B"][0], pd.to_datetime(g.gameday).to_numpy())}
RHO_EST, RHO_TXT = {}, {}
for sport, (clv, day) in PROXY.items():
    r = icc(clv, day)
    perm_p = np.mean([icc(grng.permutation(clv), day) >= r for _ in range(2000)])
    k = pd.factorize(day)[0]
    groups = [np.flatnonzero(k == i) for i in range(k.max() + 1)]
    boots = []
    for _ in range(2000):
        pick = grng.integers(0, len(groups), len(groups))
        boots.append(icc(clv[np.concatenate([groups[i] for i in pick])],
                         np.repeat(np.arange(len(pick)), [len(groups[i]) for i in pick])))
    RHO_EST[sport] = (r, *np.quantile(boots, [0.025, 0.975]))
    RHO_TXT[sport] = (f"{sport}: {len(clv)} windy games on {len(groups)} days; same-day correlation of the "
                      f"open-to-close move {r:+.3f} (95% interval {RHO_EST[sport][1]:+.2f} to {RHO_EST[sport][2]:+.2f}; "
                      f"permutation p = {perm_p:.3f})")
RHO, RHO_STRESS = round(RHO_EST["CFB Rule B"][0], 2), round(RHO_EST["CFB Rule B"][2], 2)

# 4b. The calendar. A season's signals arrive on the dates of its windiest games. For each target volume,
#     every game at or above a wind cut-off counts, plus a fixed random share of the games at the next
#     value down, so that the last ten seasons average exactly that many from the window's start. A
#     simulated season replays one real season's dates (windy weekends cluster; November is windier).
#     CFB: FBS games with station wind 2016-25, the regular season aligned on Army-Navy (Dec 12, 2026),
#     bowls on the same calendar dates (bowl weather exists only for 2023-25, about half the bowls, so
#     bowl signals are undercounted). NFL: Weeks 5-18 with observed wind 2016-25, each game on the same
#     weekday of the same week of 2026. A path that needs more than one season's signals continues into
#     further replayed seasons (for the correlation), but only this season's dates count on the calendar.
allc = pd.read_parquet(ROOT / "cfb-weather/data/processed/games.parquet")
an = allc[(allc.season_type == "regular") & allc[["home_team", "away_team"]].isin(["Army", "Navy"]).all(axis=1)]
an = local_day(an.start_utc).groupby(an.season).max()               # Army-Navy, the last regular-season Saturday
cw = allc[((allc.home_division == "fbs") | (allc.away_division == "fbs")) & (allc.wx_src == "station")
          & allc.wx_wind.notna() & allc.close_total.notna() & allc.season.between(2016, 2025)].copy()
cw["day"] = local_day(cw.start_utc)
reg = cw[cw.season_type == "regular"].copy()
reg["d26"] = (pd.Timestamp("2026-12-12") - (reg.season.map(an) - reg.day)).clip(upper=pd.Timestamp("2026-12-12"))
reg = reg[reg.d26 >= pd.Timestamp("2026-10-01")].copy()
bowl = cw[cw.season_type == "postseason"].copy()
bowl["d26"] = pd.to_datetime(dict(year=np.where(bowl.day.dt.month >= 8, 2026, 2027), month=bowl.day.dt.month,
                                  day=bowl.day.dt.day))
n26 = pd.read_parquet(ROOT / "nfl-weather/data/processed/games.parquet")
sun26 = pd.to_datetime(n26[(n26.season == 2026) & (n26.game_type == "REG")].groupby("week").gameday
                       .agg(lambda s: s.value_counts().idxmax()))
nfl = n26[(n26.game_type == "REG") & (n26.week >= 5) & n26.wx_src.isin(["gamebook", "era5"]) & n26.wx_wind.notna()
          & n26.season.between(2016, 2025)].copy()
DOW = {"Wednesday": -4, "Thursday": -3, "Friday": -2, "Saturday": -1, "Sunday": 0, "Monday": 1, "Tuesday": 2}
nfl["d26"] = nfl.week.map(sun26) + pd.to_timedelta(nfl.weekday.map(DOW), unit="D")
for part in (reg, bowl, nfl):
    part["u"] = grng.random(len(part))                              # fixed tie-break for the thinning
CAL = {  # sport: (window start, regular-season end, parts whose seasons combine one each, volumes a season)
    "CFB Rule B": (pd.Timestamp("2026-10-01"), pd.Timestamp("2026-12-12"), [reg, bowl], (25, 40, 55)),
    "NFL Rule B": (pd.Timestamp("2026-10-08"), pd.Timestamp("2027-01-10"), [nfl], (17, 25))}


def calendars(parts, start, volume):
    """Wind cut-off, realised 2016-25 average, and every season pattern as sorted days after `start`."""
    ws = np.unique(np.concatenate([p.wx_wind.to_numpy() for p in parts]))
    avg = sum((len(p) - np.searchsorted(np.sort(p.wx_wind.to_numpy()), ws)) / p.season.nunique() for p in parts)
    i = int(np.argmax(avg <= volume))                               # strictest cut-off at or under the target
    hi, lo = ws[i], ws[i - 1]
    q = (volume - avg[i]) / (avg[i - 1] - avg[i])                   # share of the games at `lo` to add
    per = []
    for p in parts:
        k = p[(p.wx_wind >= hi) | ((p.wx_wind == lo) & (p.u < q))]
        per.append([(k.d26[k.season == s] - start).dt.days.sort_values().to_numpy() for s in sorted(p.season.unique())])
    pats = [np.sort(np.concatenate(combo)) for combo in itertools.product(*per)]
    realised = sum(np.mean([len(d) for d in pp]) for pp in per)
    return (lo + hi) / 2, realised, pats


def season_draws(pats, sims):
    """Settle day of each of the first NMAX signals (days after the window start; nan once this season
    runs out), a same-day cluster index (continuing into further replayed seasons when needed), and the
    number of signals this season."""
    first = grng.integers(len(pats), size=sims)
    day = np.full((sims, NMAX), np.nan)
    cid = np.empty((sims, NMAX), dtype=int)
    for i in range(sims):
        d = pats[first[i]]
        seq, n, off = [d], len(d), 1000
        while n < NMAX:
            e = pats[grng.integers(len(pats))] + off
            seq.append(e)
            n, off = n + len(e), off + 1000
        s = np.concatenate(seq)[:NMAX]
        day[i, :min(len(d), NMAX)] = d[:NMAX]
        cid[i] = np.concatenate([[0], np.cumsum(np.diff(s) != 0)])
    return day, cid, np.array([len(pats[f]) for f in first])


PATS = {}
for sport, (start, _, parts, volumes) in CAL.items():
    for vol in volumes:
        PATS[sport, vol] = calendars(parts, start, vol)


def noise(sport, e, V, cid, rho):
    """CLV noise around the scenario mean: the resampled, centred historical moves, plus (when correlated) a
    shared same-day part; the total spread is unchanged."""
    if cid is None or rho == 0:
        return e
    sd = PROXY[sport][0].std()
    return np.sqrt(1 - rho) * e + np.sqrt(rho) * sd * np.take_along_axis(V, cid, axis=1)


# 4c. Thresholds for the gates this section adds: each sequential boundary (c), and a single-look t test at
#     20, 30 or 40 signals. Calibrated per sport under no edge, at every share of zero-CLV signals, with
#     signals independent and with same-day correlation at each season volume; the strictest is kept,
#     rounded up to 0.01, so each holds in every one of those cases. The issue's own gates keep their
#     textbook thresholds (t > 1.65, bootstrap bounds), so their false-pass rates show what correlation does.
need = []
for sport in PROXY:
    clv = PROXY[sport][0]
    e = clv[grng.integers(0, len(clv), (CALSIMS, NMAX))] - clv.mean()
    u, V = grng.random((CALSIMS, NMAX)), grng.standard_normal((CALSIMS, NMAX))
    cases = [(IND, None, None)] + [(COR, vol, season_draws(PATS[sport, vol][2], CALSIMS)[1]) for vol in CAL[sport][3]]
    for dep, vol, cid in cases:
        x0 = noise(sport, e, V, cid, RHO)
        for z in ZERO_SHARES:
            tt = np.nan_to_num(running(np.where(u < z, 0.0, x0))[1], nan=-np.inf)
            row = dict(sport=sport, dependence=dep, volume=vol, zero_share=z)
            for shape, h in SHAPES.items():
                m = (tt[:, LOOK0 - 1:] / h).max(axis=1)
                for a in ALPHAS:
                    need.append(dict(row, gate=f"sequential {shape} {a:.0%}", signals=f"{LOOK0}-{NMAX}",
                                     c_needed=np.quantile(m, 1 - a)))
            for n in (20, 30, 40):
                need.append(dict(row, gate="t > calibrated 5%", signals=str(n), c_needed=np.quantile(tt[:, n - 1], 0.95)))
need = pd.DataFrame(need)
BOUND = {k: np.ceil(d.c_needed.max() * 100) / 100 for k, d in need.groupby(["sport", "gate", "signals"])}
BOUND_IND = {k: np.ceil(d.c_needed.max() * 100) / 100
             for k, d in need[need.dependence == IND].groupby(["sport", "gate", "signals"])}
del e, u, V, x0, tt, m


def gate_list(sport, mean, t, lb, f):
    """(gate, signals, passes, signal count at the decision or the pass, threshold) for one floor."""
    full = lambda n: np.full(len(t), n)  # noqa: E731
    out = [("mean CLV > 0 (today's gate)", "20", floor_ok(mean[:, 19], f), full(20), None)]
    for n in (20, 30, 40):
        ok = floor_ok(mean[:, n - 1], f)
        cn = BOUND[sport, "t > calibrated 5%", str(n)]
        out += [("t > 1.65", str(n), (t[:, n - 1] > T_CRIT) & ok, full(n), T_CRIT),
                ("bootstrap 90% lower bound > 0", str(n), (lb[n][0] > 0) & ok, full(n), None),
                ("bootstrap 95% lower bound > 0", str(n), (lb[n][1] > 0) & ok, full(n), None),
                ("t > calibrated 5%", str(n), (t[:, n - 1] > cn) & ok, full(n), cn)]
    for shape, h in SHAPES.items():
        for a in ALPHAS:
            gate = f"sequential {shape} {a:.0%}"
            bc = BOUND[sport, gate, f"{LOOK0}-{NMAX}"]
            hit = (t[:, LOOK0 - 1:] > bc * h) & floor_ok(mean[:, LOOK0 - 1:], f)
            p = hit.any(axis=1)
            out.append((gate, f"{LOOK0}-{NMAX}", p, np.where(p, hit.argmax(axis=1) + LOOK0, NMAX), bc))
    if f == 0:
        out.append(("registered keep test (reference)", "40", (mean[:, NMAX - 1] > 0) & (t[:, NMAX - 1] > KEEP_T),
                    full(NMAX), KEEP_T))
    return out


# 4d. Every gate and scenario, with signals independent (the issue's set-up, every floor and zero share), with
#     same-day correlation at each season volume, and a stress case at CFB's upper-bound correlation for the
#     middle volume. Then each gate on the calendar (no zero-CLV signals). The same draws are reused across
#     scenarios, zero shares and dependence cases.
gate_rows, date_rows = [], []
for sport, (start, reg_end, _, volumes) in CAL.items():
    clv = PROXY[sport][0]
    e = clv[grng.integers(0, len(clv), (GSIMS, NMAX))] - clv.mean()
    u, V = grng.random((GSIMS, NMAX)), grng.standard_normal((GSIMS, NMAX))
    draws = {vol: season_draws(PATS[sport, vol][2], GSIMS) for vol in volumes}
    mid = volumes[(len(volumes) - 1) // 2]
    for dep, vol, rho in [(IND, None, 0.0)] + [(COR, v, RHO) for v in volumes] + [(STRESS, mid, RHO_STRESS)]:
        base0 = noise(sport, e, V, None if vol is None else draws[vol][1], rho)
        for scen, cut in SCEN:
            base = base0 + (1 - cut) * clv.mean()
            for z in ZERO_SHARES:
                x = np.where(u < z, 0.0, base)
                mean, t = running(x)
                keep = (mean[:, NMAX - 1] > 0) & (t[:, NMAX - 1] > KEEP_T)
                lb = {n: boot_lower(x[:, :n], [0.10, 0.05]) for n in (20, 30, 40)}
                for f in (FLOORS if dep == IND else (0.0,)):
                    for gate, n, p, stop, bc in gate_list(sport, mean, t, lb, f):
                        seq = gate.startswith("sequential")
                        gate_rows.append(dict(
                            section="gates", sport=sport, dependence=dep, rho=rho, volume=vol, scenario=scen,
                            scenario_mean_clv=x.mean(), zero_share=z, gate=gate, signals=n, floor=f, threshold=bc,
                            p_pass=p.mean(), p_pass_then_not_kept_at_40=(p & ~keep).mean(),
                            mean_signals_to_pass=stop[p].mean() if seq and p.any() else np.nan,
                            median_signals_to_pass=np.median(stop[p]) if seq and p.any() else np.nan,
                            p_no_pass_by_40=1 - p.mean() if seq else np.nan))
                        if f != 0 or z != 0:
                            continue
                        for dvol in (volumes if vol is None else (vol,)):
                            day = np.take_along_axis(draws[dvol][0], (stop - 1)[:, None], axis=1)[:, 0]
                            won, dec = p & ~np.isnan(day), ~np.isnan(day)
                            staked = np.where(won, draws[dvol][2] - stop, 0)     # real-money bets left this season
                            date_rows.append(dict(
                                section="dates", sport=sport, dependence=dep, rho=rho, volume=dvol, scenario=scen,
                                zero_share=z, gate=gate, signals=n, floor=0.0,
                                wind_cutoff=PATS[sport, dvol][0], avg_signals_in_history=PATS[sport, dvol][1],
                                p_decided_by_reg_end=(day <= (reg_end - start).days).mean(),
                                p_decided_by_season_end=dec.mean(),
                                median_decision_date=(start + pd.Timedelta(days=float(np.median(day[dec])))).date()
                                if dec.any() else None,
                                p_pass_by_reg_end=(p & (day <= (reg_end - start).days)).mean(),
                                p_pass_by_season_end=won.mean(),
                                median_pass_date=(start + pd.Timedelta(days=float(np.median(day[won])))).date()
                                if won.any() else None,
                                median_weeks_to_pass=np.median(day[won]) / 7 if won.any() else np.nan,
                                mean_staked_bets_this_season=staked.mean()))
G, Dt = pd.DataFrame(gate_rows), pd.DataFrame(date_rows)

# 4e. Betting from the first signal while the gate is undecided: flat 0.5% of starting bankroll a bet at
#     -110, no pushes. Exact binomial arithmetic, not advice. 1 unit = one bet = 0.5% of bankroll.
stake_rows = []
for n in (20, 40):
    w = np.arange(n + 1)
    units = w * PAYOUT - (n - w)
    for label, p in (("no edge", 0.5), ("half the edge", (0.566 + 0.5) / 2),
                     ("historical edge (CFB windy unders)", 0.566)):
        pmf, mu = stats.binom.pmf(w, n, p), n * (p * PAYOUT - (1 - p))
        lo, hi = units[int(stats.binom.ppf(0.05, n, p))], units[int(stats.binom.ppf(0.95, n, p))]
        stake_rows.append(dict(section="stakes", bets=n, scenario=f"{label}, {100 * p:.1f}% at -110",
                               mean_units=mu, p5_units=lo, p95_units=hi, p_behind=pmf[units < 0].sum(),
                               mean_pct_bankroll=mu * STAKE, p5_pct_bankroll=lo * STAKE, p95_pct_bankroll=hi * STAKE))
St = pd.DataFrame(stake_rows)
pd.concat([G, Dt, St], ignore_index=True).to_csv(OUT / "money_gate.csv", index=False, float_format="%.4g")

# ---- console, also saved as output/money_gate.log
piv = dict(columns=["sport", "scenario"], sort=False)
say(f"\nPaper-to-money gate (issue #51): {GSIMS:,} simulated CLV paths per cell; 0 variants")
for txt in RHO_TXT.values():
    say(txt)
say(f"Simulated same-day correlation: {RHO} (CFB's estimate) for both sports; stress case {RHO_STRESS} "
    f"(CFB's upper bound)")
say("\nThresholds this section calibrates (sequential: the t statistic after each settled signal, 10th to 40th, "
    "must exceed c, or c * sqrt(40 / n) for OBF). Needed under no edge, worst over the three zero shares:")
say(need.pivot_table(index=["gate", "signals"], columns=["sport", "dependence", "volume"], values="c_needed",
                     aggfunc="max", sort=False).round(2).to_string())
say("Used (strictest case, rounded up), and what independent signals alone would need:")
for k, v in BOUND.items():
    say(f"  {k[0]}, {k[1]} at {k[2]}: {v:.2f} (independent alone {BOUND_IND[k]:.2f})")
ind0 = G[(G.dependence == IND) & (G.floor == 0) & (G.zero_share == 0)]
say("\nPass rate by 40 signals, independent signals (the issue's set-up), no zero-CLV signals, no floor\n"
    + ind0.pivot_table(index=["gate", "signals"], values="p_pass", **piv).round(3).to_string())
cor0 = G[(G.dependence != IND) & (G.zero_share == 0)]
say(f"\nPass rate by 40 signals with same-day correlation {RHO} by season volume, and the stress case at "
    f"{RHO_STRESS} (no zeros, no floor)\n"
    + cor0.pivot_table(index=["gate", "signals"], columns=["sport", "dependence", "volume", "scenario"], values="p_pass",
                       sort=False).round(3).to_string())
say("\nSequential gates: signals to pass (mean, when it passes) and the chance of no pass by 40\n"
    + G[(G.zero_share == 0) & G.gate.str.startswith("sequential") & (G.dependence != STRESS)].pivot_table(
        index=["gate"], columns=["sport", "dependence", "volume", "scenario"],
        values=["mean_signals_to_pass", "p_no_pass_by_40"], sort=False).round(2).T.to_string())
say("\nMinimum mean CLV floors (0, 0.25, 0.5 points), independent, no zeros\n"
    + G[(G.dependence == IND) & (G.zero_share == 0)].pivot_table(
        index=["gate", "signals", "floor"], values="p_pass", **piv).round(3).to_string())
say("\nShare of signals with CLV exactly 0 (0, 20%, 40%), independent, no floor\n"
    + G[(G.dependence == IND) & (G.floor == 0)].pivot_table(
        index=["gate", "signals", "zero_share"], values="p_pass", **piv).round(3).to_string())
mids = {s: v[3][(len(v[3]) - 1) // 2] for s, v in CAL.items()}
cz = G[(G.dependence == COR) & (G.volume == G.sport.map(mids))]
say("\nShare of signals with CLV exactly 0, with same-day correlation, CFB 40 and NFL 17 a season\n"
    + cz.pivot_table(index=["gate", "signals", "zero_share"], values="p_pass", **piv).round(3).to_string())
say("\nPasses, then fails the registered keep test at 40 (same-day correlation, CFB 40 and NFL 17 a season, "
    "no zeros)\n" + cz[cz.zero_share == 0].pivot_table(index=["gate", "signals"], values="p_pass_then_not_kept_at_40",
                                                       **piv).round(3).to_string())
say("\nCalendar, same-day correlated signals, no zeros: chance the gate has decided / passed by the regular-season "
    "end and by the season end, and the median pass date")
for (sport, vol), d in Dt[Dt.dependence == COR].groupby(["sport", "volume"], sort=False):
    r = d.iloc[0]
    say(f"\n{sport}, {vol} signals a season (wind cut-off about {r.wind_cutoff:.1f} mph; "
        f"{r.avg_signals_in_history:.1f} a season in 2016-25)")
    say(d.pivot_table(index=["gate", "signals"], columns="scenario", sort=False,
                      values=["p_decided_by_season_end", "p_pass_by_reg_end", "p_pass_by_season_end",
                              "mean_staked_bets_this_season"]).round(2).to_string())
    say(d[d.scenario != "no edge"].pivot_table(index=["gate", "signals"], columns="scenario", sort=False,
                                               values="median_pass_date", aggfunc="first").to_string())
say("\nBetting from the first signal: bankroll change (1 unit = 0.5% of bankroll)\n"
    + St.drop(columns="section").round(2).to_string(index=False))
(OUT / "money_gate.log").write_text("\n".join(LOG).lstrip("\n") + "\n")
