"""The weather board: forecast weather for upcoming games, the historical scoring
effect of that weather, how much closing totals usually move for it, the model's
P(under), and (when a key is configured) Pinnacle's live total and de-vigged price.
Shared by scripts/this_week.py and scripts/alerts.py."""
from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import fetch
from .build import load_schedule
from .config import OUT, PROC, ROOT
from .features import BIN_TERMS, LABELS, add_weather_features
from .market import (MIN_UNDER_ODDS, cohort_residuals, ev_under, fit_under_model, load_games, market_p_under,
                     predict_under)
from .models import fit
from .weather import game_weather

RETRACTABLE = {"ATL97", "DAL00", "HOU00", "IND00", "PHO00"}
RULES_VERSION = "v2-2026-09-28"  # PREREGISTRATION.md amendment 2
LEAN_P = 0.55  # pre-registered (PREREGISTRATION.md)
RULE_B_WIND, RULE_B_LEAD = 15, (1, 3)  # Rule B: forecast wind >= 15 mph, 1-3 days before kickoff
PRICING_LAST_SEASON = 2023             # frozen: pricing cohorts use seasons <= 2023 only


def rule_b_status(r):
    """Why a game is or isn't an actionable Rule B (early wind under) signal.
    Only "SIGNAL" is actionable; everything else says what's missing."""
    if r.wx_src != "era5":
        return "not_outdoor"
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


def best_under(totals: pd.DataFrame, rule_book="pinnacle") -> pd.DataFrame:
    """Per event, the best under price any logged book offers at the rule book's total, and
    which book. Logging only (line shopping); Rule B still prices at the rule book."""
    rule = totals[totals.book == rule_book][["event_id", "total"]]
    same = totals.dropna(subset=["total", "under_price"]).merge(rule, on=["event_id", "total"])
    best = same.sort_values("under_price", ascending=False).drop_duplicates("event_id")
    return best[["event_id", "under_price", "book"]].rename(columns={"under_price": "best_under",
                                                                    "book": "best_under_book"})


def _pinnacle_live():
    from . import oddsapi
    try:
        df = oddsapi.live(markets=("totals",))
    except SystemExit as e:  # no key, out of credits, API down: board still works on nflverse lines
        print(f"  Pinnacle unavailable: {e}")
        return None
    if df.empty:
        return None
    df = df[df.market == "totals"].copy()
    pin = df[df.book == oddsapi.RULE_BOOK].merge(best_under(df, oddsapi.RULE_BOOK), on="event_id", how="left")
    pin["gameday"] = pd.to_datetime(pin.commence_utc, utc=True).dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    return pin.rename(columns={"home": "home_team", "away": "away_team", "total": "pin_total",
                               "over_price": "pin_over", "under_price": "pin_under"})[
        ["home_team", "away_team", "gameday", "pin_total", "pin_over", "pin_under", "best_under", "best_under_book",
         "snapshot_utc"]]


def compute(days=8, refresh=True, pinnacle=False):
    """`pinnacle`: price at live Pinnacle (1 Odds API credit; quota.py may skip it when credits are low)."""
    if refresh:
        fetch.fetch_schedule()
    games = load_schedule()
    today = pd.Timestamp(date.today())
    up = games[games.result.isna() & games.date.between(today, today + timedelta(days=days))].copy()
    if up.empty:
        return up
    if refresh:
        fetch.fetch_forecasts(up, days_ahead=days)

    cal = json.loads((PROC / "calibration.json").read_text())
    up = up.merge(game_weather(up, kind="forecast"), on="game_id", how="left")
    closed = up.roof.isin(["dome", "closed"]) | (up.roof.isna() & up.stadium_key.isin(RETRACTABLE))
    # open retractable roofs are their own category in training (no weather terms); match that here
    open_roof = up.roof.eq("open") & ~closed
    up["wx_src"] = np.select([closed, open_roof, up.om_temp.notna()], ["indoor", "open_roof", "era5"], "missing")
    up["wx_wind"] = (cal["wind_intercept"] + cal["wind_slope"] * up.om_wind).clip(lower=0)
    up["wx_temp"] = cal["temp_intercept"] + cal["temp_slope"] * up.om_temp
    up["wx_precip"], up["wx_snow"] = up.om_precip, up.om_snow
    up["indoor"] = closed.astype(int)
    up["roof_open"] = open_roof.astype(int)
    up = add_weather_features(up)

    hist = load_games()
    fx = ["home_ts", "away_ts", "week_fe"]
    act = fit(hist, "total", BIN_TERMS + ["playoff", "neutral"], fx, "hetero").set_index("term").coef
    mkt = fit(hist, "total_line", BIN_TERMS + ["playoff", "neutral"], fx, "hetero").set_index("term").coef
    wx = [t for t in BIN_TERMS if t not in ("indoor", "roof_open")]
    up["pts_effect"] = sum(up[t] * act.get(t, 0) for t in wx)
    up["mkt_adjust"] = sum(up[t] * mkt.get(t, 0) for t in wx)
    up["p_under"] = predict_under(fit_under_model(hist), up)
    up["lead_days"] = (up.date - today).dt.days

    # market: Pinnacle when available, else the nflverse line and prices
    up["line_src"] = "nflverse"
    up["mkt_total"], up["mkt_under"], up["mkt_over"] = up.total_line, up.under_odds, up.over_odds
    up["best_under"], up["best_under_book"] = np.nan, ""
    if pinnacle:
        pin = _pinnacle_live()
        if pin is not None and len(pin):
            up = up.drop(columns=["best_under", "best_under_book"]).merge(
                pin, on=["home_team", "away_team", "gameday"], how="left")
            up["best_under_book"] = up.best_under_book.fillna("")
            has = up.pin_total.notna()
            up.loc[has, ["mkt_total", "mkt_under", "mkt_over"]] = up.loc[has, ["pin_total", "pin_under", "pin_over"]].values
            up.loc[has, "line_src"] = "pinnacle"
    up["p_market"] = market_p_under(up.mkt_under, up.mkt_over, "shin")
    up["edge"] = up.p_under - up.p_market

    # line- and price-aware value of the under at the posted number, from the
    # frozen (<= 2023) cohort of outdoor games with 15+ mph wind
    frozen = hist[hist.season <= PRICING_LAST_SEASON]
    resid = cohort_residuals(frozen, (frozen.outdoor == 1) & (frozen.wx_wind >= RULE_B_WIND))
    up["ev_under"] = ev_under(up.mkt_total, up.mkt_under, up.mkt_total, resid)
    up["rule_b"] = up.apply(rule_b_status, axis=1)

    # visitor's climate for the acclimation watch: dome status from its latest team-season,
    # and its home city's mean temperature over the last available 7 days (NOAA GHCN-D)
    from .build import FRANCHISE, _practice_temps
    tg = pd.read_parquet(PROC / "team_games.parquet", columns=["team", "franchise", "season", "dome_team", "station"])
    latest = tg.sort_values("season").drop_duplicates("franchise", keep="last")
    pt = _practice_temps().dropna(subset=["tavg7"]).sort_values("date").drop_duplicates("station", keep="last")
    latest = latest.merge(pt[["station", "tavg7"]], on="station", how="left")
    up["away_franchise"] = up.away_team.replace(FRANCHISE)
    up = up.merge(latest[["franchise", "dome_team", "tavg7"]].rename(
        columns={"franchise": "away_franchise", "dome_team": "v_dome", "tavg7": "v_city_temp7"}), on="away_franchise", how="left")

    def conditions(r):
        if r.wx_src == "indoor":
            return "indoor"
        if r.wx_src == "missing":
            return "no forecast yet"
        tags = [f"{r.wx_wind:.0f} mph", f"{r.wx_temp:.0f}°F"]
        tags += ["snow"] if r.snow else ["rain"] if r.rain else []
        return ", ".join(tags)

    up["conditions"] = up.apply(conditions, axis=1)
    up["flags"] = up.apply(lambda r: ", ".join(LABELS[t] for t in wx if r[t]), axis=1)
    up["lean"] = np.where(up.wx_src != "era5", "", np.where(up.p_under >= LEAN_P, "UNDER lean",
                                                            np.where(up.p_under <= 1 - LEAN_P, "OVER lean", "")))
    return up.sort_values(["gameday", "gametime"])


BOARD_COLS = ["gameday", "gametime", "away_team", "home_team", "stadium", "lead_days", "conditions", "flags", "line_src",
              "mkt_total", "mkt_under", "total_line", "spread_line", "pts_effect", "mkt_adjust", "p_under", "p_market",
              "edge", "ev_under", "rule_b", "lean"]


def save(up):
    """Write output/this_week.csv and append every game (not just leans) to the
    forward-test ledger defined in PREREGISTRATION.md."""
    up[BOARD_COLS].to_csv(OUT / "this_week.csv", index=False)
    path = ROOT / "data" / "forward" / "ledger.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    snap = up[["game_id", "gameday", "gametime", "away_team", "home_team", "lead_days", "wx_src", "wx_wind", "wx_temp",
               "wx_precip", "wx_snow", "line_src", "mkt_total", "mkt_under", "mkt_over", "p_under", "p_market", "lean",
               "ev_under", "rule_b", "best_under", "best_under_book"]].copy()
    snap = snap.rename(columns={"mkt_total": "total_line", "mkt_under": "under_odds", "mkt_over": "over_odds"})
    snap.insert(0, "snapshot_utc", pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"))
    snap.insert(1, "rules_version", RULES_VERSION)
    if path.exists():  # older ledgers lack the v2 columns: rewrite once with the union of columns
        old = pd.read_csv(path)
        if list(old.columns) != list(snap.columns):
            pd.concat([old, snap], ignore_index=True)[list(snap.columns)].to_csv(path, index=False)
            return
    snap.to_csv(path, mode="a", header=not path.exists(), index=False)
