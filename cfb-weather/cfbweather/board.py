"""College football weather board: upcoming FBS games, the kickoff forecast on the
station scale (frozen calibration), the posted DraftKings total and prices (via
ESPN), and each game's Rule B status. Same gates as nfl-weather's v2 rule: a
signal needs forecast wind >= 15 mph 1-3 days out, a posted total, an under price
of -115 or better, and positive expected value at that line and price."""
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

RULES_VERSION = "cfb-v1-2026-09-28"
RULE_B_WIND, RULE_B_LEAD = 15, (1, 3)
PRICING_LAST_SEASON = 2023


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


def odds_team_names():
    """The Odds API's "School Mascot" names -> cfbfastR school names, including alternate names."""
    ti = pd.read_parquet(sorted((RAW / "cfbfastr").glob("team_info_*.parquet"))[-1])
    names = {f"{a} {b}": a for a, b in zip(ti.school, ti.mascot)}
    for alt in ("alt_name1", "alt_name2", "alt_name3"):  # e.g. "UMass Minutemen" for Massachusetts
        for a, m, school in zip(ti[alt], ti.mascot, ti.school):
            if isinstance(a, str) and a:
                names.setdefault(f"{a} {m}", school)
    return names


def compute(days=8, refresh=True, prices=True):
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
    names = odds_team_names()
    # prices=False (dry runs) skips The Odds API so it costs no credits
    oa = fetch.odds_api_totals(names) if prices else pd.DataFrame(columns=["home_team", "away_team"])
    oa = oa.dropna(subset=["home_team", "away_team"])
    if len(oa):
        oa["day"] = pd.to_datetime(oa.commence_utc, utc=True).dt.strftime("%Y-%m-%d")
        up["day"] = up.start_utc.dt.strftime("%Y-%m-%d")
        up = up.merge(oa.drop(columns="commence_utc"), on=["home_team", "away_team", "day"], how="left")
    else:
        up = up.merge(fetch.espn_week_odds(days), on="game_id", how="left")
    hist = load_games(2006, PRICING_LAST_SEASON)
    resid = cohort_residuals(hist, (hist.outdoor == 1) & (hist.wx_wind >= RULE_B_WIND))
    up["ev_under"] = ev_under(up.mkt_total, up.mkt_under, up.mkt_total, resid)
    up["rule_b"] = up.apply(rule_b_status, axis=1)
    up["kick_et"] = up.start_utc.dt.tz_convert("America/New_York").dt.strftime("%a %m-%d %H:%M")
    return up.sort_values("start_utc")


COLS = ["game_id", "kick_et", "away_team", "home_team", "venue", "lead_days", "wx_src", "wx_wind", "wx_temp",
        "wx_precip", "line_src", "mkt_total", "mkt_under", "mkt_over", "ev_under", "rule_b"]


def save(up):
    up[COLS].to_csv(OUT / "this_week.csv", index=False)
    path = ROOT / "data" / "forward" / "ledger.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    snap = up[COLS + ["start_utc"]].copy()
    snap.insert(0, "snapshot_utc", pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"))
    snap.insert(1, "rules_version", RULES_VERSION)
    snap.to_csv(path, mode="a", header=not path.exists(), index=False)
