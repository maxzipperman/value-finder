"""Quick screens of candidate betting theses on data already in this repo (no downloads, no API calls).

These are descriptive checks to decide which ideas deserve a pre-registered forward test. They are
not strategies: thresholds come from the cited papers (or are round numbers fixed before looking),
lines are closing lines, and bets are flat 1 unit at -110. Every bet screen counts toward
n_variants (printed and saved), and the Bonferroni bar is reported next to it. Seasons stop at
2025, so 2026 stays clean for any forward test picked from here.

Inputs (read-only)
  nfl-weather/data/processed/games.parquet, team_games.parquet   nflverse closing lines 1999-2025; SBR opening lines 2007-21
  cfb-weather/data/processed/games.parquet                       cfbfastR consensus (median-book) closing lines 2006-2025
  sharp-markets/data/raw/nfl/kalshi_*                            cached Kalshi KXNFLTOTAL 1-min candles, 2025 season (H4a pull)

Outputs: output/screens.csv, key_numbers.csv, line_moves.csv, cfb_open_vs_close.csv, calibration_slopes.csv,
         kalshi_ladder.csv, summary.json (all under output/)
Run from the repo root:  nfl-weather/.venv/bin/python strategy-research/screen.py
"""
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nfl-weather"))

from nflweather.build import FRANCHISE  # noqa: E402  OAK->LV, SD->LAC, STL->LA
from nflweather.market import wilson  # noqa: E402

OUT = Path(__file__).resolve().parent / "output"
BE_110 = 110 / 210                      # break-even at -110
BE_TEASE_2_120 = (1 / (1 + 100 / 120)) ** 0.5   # per-leg break-even, 2-team 6-pt teaser at -120 (73.9%)
BE_TEASE_3_160 = (1 / 2.6) ** (1 / 3)            # per-leg break-even, 3-team 6-pt teaser at +160 (72.7%)
PACIFIC = {"SEA", "SF", "OAK", "LV", "SD", "LAC", "LA"}       # LA = Rams 2016+ (STL before, Central time)
EASTERN = {"NE", "NYJ", "NYG", "BUF", "MIA", "PHI", "WAS", "BAL", "PIT", "CLE", "CIN", "DET", "IND",
           "ATL", "CAR", "TB", "JAX"}
ACADEMIES = {"Army", "Navy", "Air Force"}
P5 = {"SEC", "Big Ten", "Big 12", "ACC", "Pac-12", "Big East"}   # Big East = BCS-era conference (to 2012)

rows = []


def score(screen, thesis, source, era, win, loss, breakeven=BE_110, side_note=""):
    """Flat bets; win/loss boolean arrays, pushes are neither. p-values: one-sided vs break-even, two-sided vs 50%."""
    win, loss = np.asarray(win, bool), np.asarray(loss, bool)
    w, n = int(win.sum()), int(win.sum() + loss.sum())
    lo, hi = wilson(w, n)
    rows.append(dict(
        screen=screen, thesis=thesis, source=source, era=era, bets=n, wins=w,
        win_pct=w / n if n else np.nan, win_lo=lo, win_hi=hi, breakeven=breakeven,
        roi_110=(w * 100 / 110 - (n - w)) / n if n and breakeven == BE_110 else np.nan,
        p_vs_breakeven=stats.binomtest(w, n, breakeven, alternative="greater").pvalue if n else np.nan,
        p_vs_50=stats.binomtest(w, n, 0.5).pvalue if n else np.nan, note=side_note))


def eras(df, spans):
    for a, b in spans:
        yield f"{a}–{b}", df[df.season.between(a, b)]


# ---------------------------------------------------------------- NFL
g = pd.read_parquet(ROOT / "nfl-weather/data/processed/games.parquet")
g = g[g.result.notna() & g.spread_line.notna() & g.season.between(1999, 2025)].copy()
g["neutral_site"] = g.location.eq("Neutral")
g["fav_line"] = g.spread_line.abs()                                   # points the favorite lays
g["fav_margin"] = np.where(g.spread_line > 0, g.result, -g.result)    # favorite's winning margin
reg = g[g.game_type == "REG"]
STD = [(1999, 2025), (1999, 2013), (2014, 2025), (2020, 2025)]

# Key numbers: how often games land on each margin, and on the closing number itself.
key = []
for era, d in eras(g, [(1999, 2014), (2015, 2019), (2020, 2025)]):
    m = d.result.abs()
    rec = {"era": era, "games": len(d)}
    rec.update({f"margin_{k}": (m == k).mean() for k in (1, 2, 3, 4, 6, 7, 8, 10, 14)})
    for L in (3, 6, 7, 10):
        s = d[d.fav_line == L]
        rec[f"push_at_{L}"] = (s.fav_margin == L).mean() if len(s) else np.nan
        rec[f"n_line_{L}"] = len(s)
    key.append(rec)

# Wong teasers: favorites 7.5-8.5 teased to 1.5-2.5, underdogs 1.5-2.5 teased to 7.5-8.5 (6 points, closing lines).
fav_leg = g.fav_line.between(7.5, 8.5)
dog_leg = g.fav_line.between(1.5, 2.5)
tw = np.where(fav_leg, g.fav_margin > g.fav_line - 6, g.fav_margin < g.fav_line + 6)
tl = np.where(fav_leg, g.fav_margin < g.fav_line - 6, g.fav_margin > g.fav_line + 6)
leg = fav_leg | dog_leg
for era, d in eras(g[leg].assign(w=tw[leg], l=tl[leg]), STD + [(2022, 2025)]):
    score("NFL: Wong teaser legs", "6-pt teaser through 3 and 7 (Wong 2001)", "Wong, Sharp Sports Betting (2001)",
          era, d.w, d.l, BE_TEASE_2_120, "break-even = 2-team at -120")
lt = g[leg].assign(w=tw[leg], l=tl[leg])
for lab, m in {"total <= 43.5": lt.total_line <= 43.5, "total 44-48.5": lt.total_line.between(44, 48.5),
               "total >= 49": lt.total_line >= 49}.items():
    d = lt[m & lt.season.between(2014, 2025)]
    score("NFL: Wong teaser legs by total", f"Wong legs, {lab}", "Wong (2001); lower totals make 6 points worth more",
          "2014–2025", d.w, d.l, BE_TEASE_2_120, "break-even = 2-team at -120")

# Home field: has the market cut home-field advantage as fast as it shrank? Bet the road team.
hn = g[~g.neutral_site]
for era, d in eras(hn, [(1999, 2013), (2014, 2019), (2020, 2025)]):
    score("NFL: road teams (HFA decline)", "Market slow to shrink home-field advantage", "FiveThirtyEight 2021; PFF 2025",
          era, d.result < d.spread_line, d.result > d.spread_line, side_note=f"mean result - line {(d.result - d.spread_line).mean():+.2f}")

# High totals -> under (Paul & Weinbach 2002: overs overbet at the top of the totals distribution).
reg_t = reg.assign(t_rel=reg.total_line - reg.groupby("season").total_line.transform("mean"))
for thr in (5, 7):
    d0 = reg_t[reg_t.t_rel >= thr]
    for era, d in eras(d0, [(2001, 2025), (2014, 2025), (2020, 2025)]):
        score("NFL: high totals under", f"Total >= season mean + {thr} -> under", "Paul & Weinbach (2002), J. Sports Econ.",
              era, d.total < d.total_line, d.total > d.total_line, side_note="1979-2000 in-sample; 2001+ is out of sample")

# Primetime unders (the popular 2022-25 trend) and Week 1 unders.
pt = reg[reg.gametime >= "19:00"]
for lab, d0 in {"all primetime": pt, "Thursday night": pt[pt.weekday == "Thursday"],
                "Sunday night": pt[pt.weekday == "Sunday"], "Monday night": pt[pt.weekday == "Monday"]}.items():
    for era, d in eras(d0, [(1999, 2025), (1999, 2013), (2014, 2021), (2022, 2025)]):
        score("NFL: primetime unders", f"{lab} -> under", "Media trend (Covers, SI, 2023-25)", era,
              d.total < d.total_line, d.total > d.total_line)
w1 = reg[reg.week == 1]
for era, d in eras(w1, STD):
    score("NFL: Week 1 unders", "Week 1 -> under (early-season rust)", "Davis, Fodor, McElfresh & Krieger (2015), J. Prediction Markets",
          era, d.total < d.total_line, d.total > d.total_line)

# Team-level rows for situational screens.
def team_rows(d):
    base = dict(game_id=d.game_id, season=d.season, week=d.week, game_type=d.game_type, gameday=d.gameday,
                gametime=d.gametime, neutral_site=d.neutral_site)
    h = pd.DataFrame({**base, "team": d.home_team, "opp": d.away_team, "home": 1, "line": -d.spread_line,
                      "margin": d.result, "rest": d.home_rest, "opp_rest": d.away_rest})
    a = pd.DataFrame({**base, "team": d.away_team, "opp": d.home_team, "home": 0, "line": d.spread_line,
                      "margin": -d.result, "rest": d.away_rest, "opp_rest": d.home_rest})
    t = pd.concat([h, a], ignore_index=True)
    t["ats"] = t.margin + t.line          # > 0 cover, < 0 no cover, 0 push
    t["franchise"] = t.team.replace(FRANCHISE)
    return t.sort_values(["franchise", "season", "gameday"]).reset_index(drop=True)


t = team_rows(g)


def bet_team(d):
    return d.ats > 0, d.ats < 0


def fade_team(d):
    return d.ats < 0, d.ats > 0


# Holdover bias (Fodor, DiFilippo, Krieger & Davis 2013): Week 1, prior-season playoff team vs non-playoff team.
po = g[g.game_type != "REG"]
po_teams = {(s + 1, FRANCHISE.get(x, x)) for s, a, b in zip(po.season, po.home_team, po.away_team) for x in (a, b)}
t["prior_playoff"] = [(s, f) in po_teams for s, f in zip(t.season, t.franchise)]
opp_pp = t.set_index(["game_id", "team"]).prior_playoff.rename("opp_prior_playoff")
t = t.join(opp_pp, on=["game_id", "opp"])
hold = t[(t.week == 1) & (t.game_type == "REG") & ~t.prior_playoff & t.opp_prior_playoff]
for era, d in eras(hold, [(1999, 2003), (2004, 2012), (2013, 2025)]):
    score("NFL: holdover bias, Week 1", "Bet non-playoff team vs last year's playoff team", "Fodor et al. (2013), Applied Financial Econ.",
          era, *bet_team(d), side_note="2004-12 = paper's sample; others out of sample")

# Bye weeks (Lopez & Bliss 2024: market prices a bye at ~+1 pt post-2011; measured benefit ~+0.3).
bye = t[(t.game_type == "REG") & (t.week > 1) & (t.rest >= 13) & (t.opp_rest <= 8)]
for era, d in eras(bye, [(1999, 2010), (2011, 2023), (2024, 2025), (2011, 2025)]):
    score("NFL: fade teams off a bye", "Bet against the rested team", "Lopez & Bliss (2024), Frontiers Behav. Econ.",
          era, *fade_team(d), side_note="their sample 2002-23; 2024-25 out of sample")
for lab, d in {"bye team at home": bye[bye.home == 1], "bye team on road": bye[bye.home == 0]}.items():
    d = d[d.season.between(2011, 2025)]
    score("NFL: fade teams off a bye", f"Bet against the rested team, {lab}", "Lopez & Bliss (2024)", "2011–2025", *fade_team(d))

# Circadian edge (Smith et al. 1997, 2013): Pacific-time team vs Eastern-time team.
def zone(team):
    return "P" if team in PACIFIC else "E" if team in EASTERN else "O"


t["zone"], t["opp_zone"] = t.team.map(zone), t.opp.map(zone)
we = t[(t.zone == "P") & (t.opp_zone == "E") & ~t.neutral_site]
for lab, d0 in {"kickoff 8pm ET or later": we[we.gametime >= "20:00"], "kickoff 1pm ET (control)": we[we.gametime == "13:00"]}.items():
    for era, d in eras(d0, [(1999, 2011), (2012, 2025)]):
        score("NFL: West Coast team at night", f"Bet Pacific team vs Eastern team, {lab}", "Smith, Guilleminault & Efron (1997); Smith et al. (2013)",
              era, *bet_team(d), side_note="published sample 1970-2011; 2012-25 out of sample")

# Overreaction to last game (Vergin 2001): fade a team that covered by 14+; back one that missed by 14+ (control).
t["prev_ats"] = t.groupby(["franchise", "season"]).ats.shift(1)
nxt = t[(t.game_type == "REG") & t.prev_ats.notna()]
opp_prev = nxt.set_index(["game_id", "team"]).prev_ats.rename("opp_prev_ats")
nxt = nxt.join(opp_prev, on=["game_id", "opp"])
big_up = nxt[(nxt.prev_ats >= 14) & ~(nxt.opp_prev_ats >= 14)]
big_dn = nxt[(nxt.prev_ats <= -14) & ~(nxt.opp_prev_ats <= -14)]
for era, d in eras(big_up, STD):
    score("NFL: overreaction to last game", "Fade team that covered by 14+ last week", "Vergin (2001), Applied Financial Econ.", era, *fade_team(d))
for era, d in eras(big_dn, STD):
    score("NFL: overreaction to last game", "Back team that missed by 14+ last week (control)", "Vergin (2001): no overreaction to bad games", era, *bet_team(d))

# Turnover luck: fade a team after a +3 turnover game; fade season-to-date turnover leaders (week 5+).
tg = pd.read_parquet(ROOT / "nfl-weather/data/processed/team_games.parquet")
tg = tg[tg.season.between(1999, 2025)][["game_id", "team", "opp", "turnovers"]]
tg = tg.merge(tg.rename(columns={"team": "opp", "opp": "team", "turnovers": "takeaways"}), on=["game_id", "team", "opp"])
t = t.merge(tg.assign(to_margin=tg.takeaways - tg.turnovers)[["game_id", "team", "to_margin"]], on=["game_id", "team"], how="left")
grp = t.groupby(["franchise", "season"]).to_margin
t["prev_to"] = grp.shift(1)
t["std_to"] = grp.transform(lambda s: s.shift(1).expanding().mean())
t["n_prior"] = t.groupby(["franchise", "season"]).cumcount()
opp_to = t.set_index(["game_id", "team"])[["prev_to", "std_to"]].rename(columns=lambda c: "opp_" + c)
t = t.join(opp_to, on=["game_id", "opp"])
r = t[t.game_type == "REG"]
for lab, d0 in {"previous game TO margin >= +3": r[(r.prev_to >= 3) & ~(r.opp_prev_to >= 3)],
                "season TO margin >= +1.0/game, week 5+": r[(r.n_prior >= 4) & (r.std_to >= 1) & ~(r.opp_std_to >= 1)]}.items():
    for era, d in eras(d0, STD):
        score("NFL: turnover luck", f"Fade team with {lab}", "Turnovers mostly luck (Burke; Harvard HSAC 2014)", era, *fade_team(d))

# Open -> close (SBR 2007-21): which way do lines drift, and do moves continue or reverse?
oc = g[g.spread_open.notna() & g.sbr_spread_close.notna()].copy()
oc["fav_close"] = oc.sbr_spread_close.abs()
oc["fav_is_home"] = oc.sbr_spread_close > 0
oc["fav_open"] = np.where(oc.fav_is_home, oc.spread_open, -oc.spread_open)       # favorite's number at open
oc["fav_marg"] = np.where(oc.fav_is_home, oc.result, -oc.result)
oc = oc[oc.fav_close > 0]
score("NFL: bet timing", "Favorite at the opening number", "Levitt (2004); Moskowitz (2021)", "2007–2021",
      oc.fav_marg > oc.fav_open, oc.fav_marg < oc.fav_open)
score("NFL: bet timing", "Favorite at the closing number (same games)", "Levitt (2004); Moskowitz (2021)", "2007–2021",
      oc.fav_marg > oc.fav_close, oc.fav_marg < oc.fav_close)
ot = g[g.total_open.notna() & g.sbr_total_close.notna()]
score("NFL: bet timing", "Under at the opening total", "Levitt (2004); Moskowitz (2021)", "2007–2021", ot.total < ot.total_open, ot.total > ot.total_open)
score("NFL: bet timing", "Under at the closing total (same games)", "Levitt (2004); Moskowitz (2021)", "2007–2021", ot.total < ot.sbr_total_close, ot.total > ot.sbr_total_close)


def move_fit(y, x):
    fit = sm.OLS(y, sm.add_constant(x)).fit(cov_type="HC1")
    return fit.params.iloc[1], fit.bse.iloc[1], fit.pvalues.iloc[1]


moves = []
mv = oc.sbr_spread_close - oc.spread_open                      # + = home got more favored
b, se, p = move_fit(oc.result - oc.sbr_spread_close, mv)
moves.append(dict(market="spread", games=len(oc), mean_fav_move=(oc.fav_close - oc.fav_open).mean(),
                  share_toward_fav=((oc.fav_close - oc.fav_open) > 0).mean(), share_away_from_fav=((oc.fav_close - oc.fav_open) < 0).mean(),
                  slope_resid_on_move=b, slope_se=se, slope_p=p))
mt = ot.sbr_total_close - ot.total_open
b, se, p = move_fit(ot.total - ot.sbr_total_close, mt)
moves.append(dict(market="total", games=len(ot), mean_move=mt.mean(), share_up=(mt > 0).mean(), share_down=(mt < 0).mean(),
                  slope_resid_on_move=b, slope_se=se, slope_p=p))

# ---------------------------------------------------------------- College football
c = pd.read_parquet(ROOT / "cfb-weather/data/processed/games.parquet")
c = c[c.result.notna() & c.home_spread.notna() & c.season.between(2006, 2025) & (c.home_spread != 0)].copy()
c["fav_line"] = c.home_spread.abs()
c["fav_margin"] = np.where(c.home_spread < 0, c.result, -c.result)
CSTD = [(2006, 2025), (2006, 2015), (2016, 2025), (2021, 2025)]

for thr in (21, 28, 35):
    d0 = c[c.fav_line >= thr]
    for era, d in eras(d0, CSTD[1:]):
        score("CFB: big underdogs", f"Underdog getting {thr}+", "Sinkey & Logan (2009): CFB favorites overpriced", era,
              d.fav_margin < d.fav_line, d.fav_margin > d.fav_line)
for lab, d0 in {"weeks 0-4": c[c.week <= 4], "weeks 5+ (control)": c[c.week >= 5]}.items():
    for era, d in eras(d0, CSTD[1:]):
        score("CFB: early-season underdogs", f"All underdogs, {lab}", "Sinkey & Logan (2009); thin early-season information", era,
              d.fav_margin < d.fav_line, d.fav_margin > d.fav_line)

ct = c[c.close_total.notna()]
acad = ct[ct.home_team.isin(ACADEMIES) | ct.away_team.isin(ACADEMIES)]
both = ct[ct.home_team.isin(ACADEMIES) & ct.away_team.isin(ACADEMIES)]
for lab, d0 in {"any service academy game": acad, "academy vs academy": both}.items():
    for era, d in eras(d0, CSTD[:3]):
        score("CFB: service academy unders", f"{lab} -> under", "Action Network / Covers trend; option offenses shorten games",
              era, d.total < d.close_total, d.total > d.close_total)
ct = ct.assign(t_rel=ct.close_total - ct.groupby("season").close_total.transform("mean"))
for thr in (7, 10):
    d0 = ct[ct.t_rel >= thr]
    for era, d in eras(d0, CSTD[1:]):
        score("CFB: high totals under", f"Total >= season mean + {thr} -> under", "Paul & Weinbach (2002), NFL analogue", era,
              d.total < d.close_total, d.total > d.close_total)

# CFB overreaction: fade a team that covered its previous game by 17+ (Sinkey & Logan: lines inflate after covers).
ch = pd.DataFrame({"game_id": c.game_id, "season": c.season, "start": c.start_utc, "team": c.home_team, "opp": c.away_team,
                   "ats": c.result + c.home_spread})
ca = pd.DataFrame({"game_id": c.game_id, "season": c.season, "start": c.start_utc, "team": c.away_team, "opp": c.home_team,
                   "ats": -c.result - c.home_spread})
cl = pd.concat([ch, ca]).sort_values(["team", "season", "start"])
cl["prev_ats"] = cl.groupby(["team", "season"]).ats.shift(1)
cl = cl.join(cl.set_index(["game_id", "team"]).prev_ats.rename("opp_prev_ats"), on=["game_id", "opp"])
cu = cl[(cl.prev_ats >= 17) & ~(cl.opp_prev_ats >= 17)]
for era, d in eras(cu, CSTD[1:]):
    score("CFB: overreaction to last game", "Fade team that covered by 17+ last game", "Sinkey & Logan (2009); Vergin (2001)", era,
          d.ats < 0, d.ats > 0)

# How much do CFB totals move from open to close, by tier? (where early bets have the most room)
co = c[c.open_total.notna() & c.close_total.notna()].copy()
co["tier"] = np.where(co.home_conference.isin(P5) & co.away_conference.isin(P5), "both Power 5", "any Group of 5 / other")
cfb_open = []
for tier, d in co.groupby("tier"):
    cfb_open.append(dict(tier=tier, games=len(d), mean_abs_move=(d.close_total - d.open_total).abs().mean(),
                         share_move_3plus=((d.close_total - d.open_total).abs() >= 3).mean(),
                         mae_open=(d.total - d.open_total).abs().mean(), mae_close=(d.total - d.close_total).abs().mean()))


# ---------------------------------------------------------------- Follow-ups on the leads (added after the first pass; counted)
hi10 = ct[ct.t_rel >= 10]
for era, d in eras(hi10, [(2016, 2019), (2020, 2022), (2023, 2025)]):
    score("CFB follow-up: high totals under", "Total >= season mean + 10 -> under, sub-era", "follow-up (2023 = running-clock rule)",
          era, d.total < d.close_total, d.total > d.close_total)
d = hi10[hi10.season.between(2016, 2025) & (hi10.roof != "dome") & ~(hi10.wx_wind >= 15)]
score("CFB follow-up: high totals under", "Total >= season mean + 10 -> under, outdoor and wind < 15", "follow-up (separate from weather rule)",
      "2016–2025", d.total < d.close_total, d.total > d.close_total)
d = hi10[hi10.season.between(2016, 2025) & hi10.open_total.notna()]
score("CFB follow-up: high totals under", "Total >= season mean + 10 -> under at the OPENING total", "follow-up (bet early)",
      "2016–2025", d.total < d.open_total, d.total > d.open_total, side_note=f"mean open->close move {(d.close_total - d.open_total).mean():+.2f}")
prev_mean = ct.groupby("season").close_total.mean().shift(1)          # known before the season: no lookahead
d = ct[(ct.close_total >= ct.season.map(prev_mean) + 10) & ct.season.between(2016, 2025)]
score("CFB follow-up: high totals under", "Total >= PRIOR-season mean + 10 -> under (no lookahead)", "follow-up (tradeable threshold)",
      "2016–2025", d.total < d.close_total, d.total > d.close_total)
nfl_prev = reg.groupby("season").total_line.mean().shift(1)
d = reg[(reg.total_line >= reg.season.map(nfl_prev) + 5) & reg.season.between(2001, 2025)]
score("NFL follow-up: high totals under", "Total >= PRIOR-season mean + 5 -> under (no lookahead)", "follow-up (tradeable threshold)",
      "2001–2025", d.total < d.total_line, d.total > d.total_line)
lo10 = ct[(ct.t_rel <= -10) & ct.season.between(2016, 2025)]
score("CFB follow-up: low totals over", "Total <= season mean - 10 -> over (mirror)", "follow-up (shrinkage check)", "2016–2025",
      lo10.total > lo10.close_total, lo10.total < lo10.close_total)
d = bye[(bye.home == 1) & bye.season.between(2024, 2025)]
score("NFL follow-up: fade home team off a bye", "Bet against the rested home team", "Lopez & Bliss (2024), out of sample", "2024–2025", *fade_team(d))

# Calibration: regress the result on the closing number. A slope below 1 means the market's numbers
# are too spread out (high totals too high, big spreads too big), i.e. results regress more than lines do.
calib = []
for name, df, y, x in (("NFL total", g, "total", "total_line"), ("NFL spread (home margin)", g, "result", "spread_line"),
                       ("CFB total", ct, "total", "close_total"), ("CFB spread (home margin)", c, "result", "home_spread")):
    spans = [(1999, 2013), (2014, 2025)] if name.startswith("NFL") else [(2006, 2015), (2016, 2025)]
    for era, d in eras(df, spans):
        xv = -d[x] if name == "CFB spread (home margin)" else d[x]      # CFB home_spread is negative when home is favored
        fit = sm.OLS(d[y], sm.add_constant(xv)).fit(cov_type="HC1")
        calib.append(dict(market=name, era=era, games=len(d), slope=fit.params.iloc[1], slope_se=fit.bse.iloc[1],
                          p_slope_eq_1=2 * stats.norm.sf(abs((fit.params.iloc[1] - 1) / fit.bse.iloc[1]))))

# ---------------------------------------------------------------- Kalshi NFL totals ladder calibration (2025)
def kalshi_ladder():
    """Price vs outcome for every cached KXNFLTOTAL strike at T-5m and T-1h before kickoff (no lookahead).

    The H4a pull cached strikes within 10.5 points of the book total, so prices run ~10-90c, not the
    deep longshots. Taker returns use the ask (YES) or 1 - bid (NO) and the unrounded taker fee
    0.07 * P * (1 - P). Standard errors are bootstrapped by game (strikes in one game share an outcome).
    """
    raw = ROOT / "sharp-markets/data/raw/nfl"
    meta = {}
    for f in glob.glob(str(raw / "kalshi_markets_hist/**/*.parquet"), recursive=True):
        r = pd.read_parquet(f).iloc[0]
        if "KXNFLTOTAL" in r.params_json:
            for m in json.loads(r.body)["markets"]:
                meta[m["ticker"]] = (m["event_ticker"], float(m["floor_strike"]), m["result"])
    recs = []
    for f in glob.glob(str(raw / "kalshi_candles/**/*.parquet"), recursive=True):
        r = pd.read_parquet(f).iloc[0]
        prm = json.loads(r.params_json)
        tk = prm["market_ticker"]
        if tk not in meta or meta[tk][2] not in ("yes", "no"):
            continue
        cs = json.loads(r.body).get("candlesticks", [])
        ends = [cd["end_period_ts"] for cd in cs]
        for lab, off, max_age in (("T-5m", 300, 1800), ("T-1h", 3600, 3600)):
            ts = prm["end_ts"] - off                     # end_ts = kickoff rounded up to the minute
            j = int(np.searchsorted(ends, ts, side="right")) - 1
            if j < 0 or ts - ends[j] > max_age:
                continue
            bid = cs[j]["yes_bid"].get("close", cs[j]["yes_bid"].get("close_dollars"))
            ask = cs[j]["yes_ask"].get("close", cs[j]["yes_ask"].get("close_dollars"))
            if bid is None or ask is None:
                continue
            bid, ask = float(bid), float(ask)
            if ask <= 0 or bid <= 0 or ask - bid > 0.10:
                continue
            ev, strike, res = meta[tk]
            recs.append(dict(snap=lab, event=ev, ticker=tk, strike=strike, bid=bid, ask=ask, mid=(bid + ask) / 2,
                             yes=int(res == "yes")))
    k = pd.DataFrame(recs)
    k["yes_pnl"] = k.yes - k.ask - 0.07 * k.ask * (1 - k.ask)                       # buy YES at the ask
    k["no_pnl"] = (1 - k.yes) - (1 - k.bid) - 0.07 * (1 - k.bid) * k.bid            # buy NO at 1 - bid
    k["bucket"] = pd.cut(k.mid, [0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1], labels=[
        "0-10", "10-20", "20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"])
    rng = np.random.default_rng(7)
    out = []
    for (snap, bkt), d in k.groupby(["snap", "bucket"], observed=True):
        evs = d.event.unique()
        by_ev = {e: x for e, x in d.groupby("event")}
        boot = []
        for _ in range(1000):
            s = pd.concat([by_ev[e] for e in rng.choice(evs, len(evs))])
            boot.append((s.yes.mean() - s["mid"].mean(), s.yes_pnl.mean(), s.no_pnl.mean()))
        boot = np.array(boot)
        out.append(dict(snap=snap, bucket=bkt, contracts=len(d), games=len(evs), mean_mid=d["mid"].mean(), yes_rate=d.yes.mean(),
                        yes_minus_mid=d.yes.mean() - d["mid"].mean(), yes_minus_mid_se=boot[:, 0].std(),
                        yes_taker_roi=d.yes_pnl.mean() / d.ask.mean(), yes_taker_pnl=d.yes_pnl.mean(), yes_taker_pnl_se=boot[:, 1].std(),
                        no_taker_pnl=d.no_pnl.mean(), no_taker_pnl_se=boot[:, 2].std()))
    return pd.DataFrame(out), k


kal, kraw = kalshi_ladder()

# ---------------------------------------------------------------- save
OUT.mkdir(exist_ok=True)
res = pd.DataFrame(rows)
n_var = len(res)
res.to_csv(OUT / "screens.csv", index=False)
pd.DataFrame(key).to_csv(OUT / "key_numbers.csv", index=False)
pd.DataFrame(moves).to_csv(OUT / "line_moves.csv", index=False)
pd.DataFrame(cfb_open).to_csv(OUT / "cfb_open_vs_close.csv", index=False)
pd.DataFrame(calib).to_csv(OUT / "calibration_slopes.csv", index=False)
kal.to_csv(OUT / "kalshi_ladder.csv", index=False)
summary = dict(n_variants=n_var, bonferroni_p=0.05 / n_var,
               nfl_games=int(len(g)), cfb_games=int(len(c)), kalshi_contract_snapshots=int(len(kraw)),
               kalshi_games=int(kraw.event.nunique()) if len(kraw) else 0,
               passes_bonferroni=res.loc[res.p_vs_breakeven < 0.05 / n_var, ["screen", "thesis", "era"]].to_dict("records"))
(OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str))

pd.set_option("display.width", 250, "display.max_rows", 500, "display.max_colwidth", 70)
show = res.assign(win=(res.win_pct * 100).round(1), lo=(res.win_lo * 100).round(1), hi=(res.win_hi * 100).round(1),
                  be=(res.breakeven * 100).round(1), p_be=res.p_vs_breakeven.round(4), p50=res.p_vs_50.round(4))
print(show[["screen", "thesis", "era", "bets", "win", "lo", "hi", "be", "p_be", "p50", "note"]].to_string(index=False))
print("\nkey numbers\n", pd.DataFrame(key).round(3).to_string(index=False))
print("\nline moves\n", pd.DataFrame(moves).round(3).to_string(index=False))
print("\ncfb open vs close\n", pd.DataFrame(cfb_open).round(3).to_string(index=False))
print("\ncalibration slopes (result on closing number)\n", pd.DataFrame(calib).round(3).to_string(index=False))
print("\nkalshi ladder\n", kal.round(3).to_string(index=False))
print(f"\nn_variants = {n_var}; Bonferroni bar p < {0.05 / n_var:.5f}; passing: {summary['passes_bonferroni']}")
