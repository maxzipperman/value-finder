"""College football weather board: upcoming FBS games, the kickoff forecast on the
station scale (frozen calibration), the posted total and prices (The Odds API, else
ESPN), and each game's status under the two pre-registered rules (STRATEGY.md):

* Rule B (wind under): same gates as nfl-weather's v2 rule. A signal needs forecast
  wind >= 15 mph 1-3 days out, a posted total, an under price of -115 or better, and
  positive expected value at that line and price.
* Rule HT (high-total under, amendment 1): a posted total >= the prior season's mean
  closing total + 10, under at -115 or better. Graded at the last quote before kickoff."""
from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import fetch
from .build import schedules, venues
from .config import OUT, PROC, RAW, ROOT
from .features import add_weather_features
from .market import MIN_UNDER_ODDS, cohort_residuals, ev_under, load_games
from .weather import summarize

RULES_VERSION = "cfb-v2-2026-09-28"   # PREREGISTRATION.md amendment 1: adds Rule HT; Rule B unchanged
RULE_B_WIND, RULE_B_LEAD = 15, (1, 3)
PRICING_LAST_SEASON = 2023
HT_MARGIN = 10                         # Rule HT: total >= prior-season mean closing total + 10
HT_FIRST_KICK = pd.Timestamp("2026-10-07T00:00:00Z")   # 2026 Week 6, the first eligible game
HT_FROZEN = {2026: 52.617539 + HT_MARGIN}              # 2025 mean (955 games) + 10; fixed before Week 6


def ht_threshold(season):
    """Rule HT threshold for a season: the prior season's mean cfbfastR consensus closing total,
    over games with a nonzero closing spread and a result (strategy-research/screen.py's set), + 10.
    2026 is frozen; later seasons compute from data the season before, which is known in advance."""
    if season in HT_FROZEN:
        return HT_FROZEN[season]
    g = pd.read_parquet(PROC / "games.parquet", columns=["season", "result", "home_spread", "close_total"])
    g = g[(g.season == season - 1) & g.result.notna() & g.home_spread.notna() & (g.home_spread != 0)
          & g.close_total.notna()]
    return g.close_total.mean() + HT_MARGIN if len(g) else np.nan


def rule_ht_status(r):
    """Rule HT (high-total under). Only "SIGNAL" counts; it is graded at the game's last
    logged quote before kickoff, so earlier SIGNAL rows are provisional."""
    if pd.isna(r.mkt_total) or pd.isna(r.mkt_under):
        return "no_price"
    if pd.isna(r.ht_threshold) or r.mkt_total < r.ht_threshold:
        return "below_threshold"
    if r.mkt_under < MIN_UNDER_ODDS:
        return "price_too_high"
    return "SIGNAL"


def rule_b_status(r):
    if r.wx_src != "forecast":
        return "not_outdoor" if r.wx_src == "indoor" else r.wx_src
    if pd.isna(r.wx_wind) or r.wx_wind < RULE_B_WIND:
        return "no_trigger"
    if not (RULE_B_LEAD[0] <= r.lead_days <= RULE_B_LEAD[1]):
        return "outside_horizon"
    if pd.isna(r.mkt_total) or pd.isna(r.mkt_under):
        return "no_price"
    if r.mkt_under < MIN_UNDER_ODDS:
        return "price_too_high"
    if not (r.ev_under > 0):
        return "negative_ev"
    return "SIGNAL"


def compute(days=8, refresh=True, odds=True):
    """`odds`: price at The Odds API when a key is set (1 credit); False (dry runs) uses ESPN only."""
    if refresh:
        fetch.fetch_cfbfastr([fetch.current_season()])
    s = schedules()
    now = pd.Timestamp.now(tz="UTC")
    up = s[(s.start_utc > now) & (s.start_utc <= now + timedelta(days=days))].copy()
    up = up[(up.home_division == "fbs") | (up.away_division == "fbs")]
    if up.empty:
        return up
    up = up.merge(venues(), on="venue_id", how="left")
    up["dome"] = up.dome.fillna(False).astype(bool)
    up["lead_days"] = (up.start_utc.dt.tz_convert("America/New_York").dt.normalize().dt.tz_localize(None)
                       - pd.Timestamp(date.today())).dt.days

    cal = json.loads((PROC / "calibration.json").read_text())
    wx = []
    for r in up[~up.dome & ~up.tbd & up.lat.notna()].itertuples():
        day = r.start_utc.strftime("%Y-%m-%d")
        w = summarize(fetch.om_forecast(r.lat, r.lon, day), r.start_utc) if refresh else None
        if w:
            wx.append(dict(game_id=r.game_id, **w))
    up = up.merge(pd.DataFrame(wx, columns=["game_id", "om_wind", "om_temp", "om_precip", "om_snow", "om_gust"]),
                  on="game_id", how="left")
    up["wx_src"] = np.select([up.dome, up.lat.isna(), up.tbd, up.om_wind.notna()],
                             ["indoor", "no_venue", "time_tbd", "forecast"], "no_forecast")
    up["wx_wind"] = (cal["wind_intercept"] + cal["wind_slope"] * up.om_wind).clip(lower=0)
    up["wx_temp"] = cal["temp_intercept"] + cal["temp_slope"] * up.om_temp
    up["wx_precip"], up["wx_snow"] = up.om_precip.fillna(0), up.om_snow.fillna(0)
    up["indoor"], up["roof_open"] = up.dome.astype(int), 0
    up = add_weather_features(up)

    # prices: The Odds API when a key is set (licensed, Pinnacle first), else ESPN/DraftKings
    d = RAW / "cfbfastr"
    ti = pd.read_parquet(sorted(d.glob("team_info_*.parquet"))[-1])
    names = {f"{a} {b}": a for a, b in zip(ti.school, ti.mascot)}
    oa = fetch.odds_api_totals(names) if odds else pd.DataFrame()
    oa = oa.dropna(subset=["home_team", "away_team"]) if len(oa) else oa
    if len(oa):
        oa["day"] = pd.to_datetime(oa.commence_utc, utc=True).dt.strftime("%Y-%m-%d")
        up["day"] = up.start_utc.dt.strftime("%Y-%m-%d")
        up = up.merge(oa.drop(columns="commence_utc"), on=["home_team", "away_team", "day"], how="left")
    else:
        up = up.merge(fetch.espn_week_odds(days), on="game_id", how="left")
    for c, v in (("best_under", np.nan), ("best_under_book", "")):
        up[c] = up[c].fillna(v) if c in up else v
    hist = load_games(2006, PRICING_LAST_SEASON)
    resid = cohort_residuals(hist, (hist.outdoor == 1) & (hist.wx_wind >= RULE_B_WIND))
    up["ev_under"] = ev_under(up.mkt_total, up.mkt_under, up.mkt_total, resid)
    up["rule_b"] = up.apply(rule_b_status, axis=1)
    up["ht_threshold"] = pd.to_numeric(up.season).astype(int).map(ht_threshold)
    up["rule_ht"] = np.where(up.start_utc >= HT_FIRST_KICK, up.apply(rule_ht_status, axis=1), "before_window")
    up["kick_et"] = up.start_utc.dt.tz_convert("America/New_York").dt.strftime("%a %m-%d %H:%M")
    return up.sort_values("start_utc")


COLS = ["game_id", "kick_et", "away_team", "home_team", "venue", "lead_days", "wx_src", "wx_wind", "wx_temp",
        "wx_precip", "line_src", "mkt_total", "mkt_under", "mkt_over", "ev_under", "rule_b", "best_under",
        "best_under_book", "ht_threshold", "rule_ht"]


def save(up):
    up[COLS].to_csv(OUT / "this_week.csv", index=False)
    path = ROOT / "data" / "forward" / "ledger.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    snap = up[COLS + ["start_utc"]].copy()
    snap.insert(0, "snapshot_utc", pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"))
    snap.insert(1, "rules_version", RULES_VERSION)
    if path.exists():  # a ledger written before new columns were added: rewrite once with the union
        old = pd.read_csv(path)
        if list(old.columns) != list(snap.columns):
            cols = list(snap.columns) + [c for c in old.columns if c not in snap.columns]
            pd.concat([old, snap], ignore_index=True).reindex(columns=cols).to_csv(path, index=False)
            return
    snap.to_csv(path, mode="a", header=not path.exists(), index=False)
