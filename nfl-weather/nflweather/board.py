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
from .market import fit_under_model, load_games, market_p_under, predict_under
from .models import fit
from .weather import game_weather

RETRACTABLE = {"ATL97", "DAL00", "HOU00", "IND00", "PHO00"}
LEAN_P = 0.55  # pre-registered (PREREGISTRATION.md)


def _pinnacle_live():
    from . import oddsapi
    try:
        df = oddsapi.live(markets=("totals",))
    except SystemExit as e:  # no key / plan problem: board still works on nflverse lines
        print(f"  Pinnacle unavailable: {e}")
        return None
    df = df[df.market == "totals"].copy()
    df["gameday"] = pd.to_datetime(df.commence_utc, utc=True).dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    return df.rename(columns={"home": "home_team", "away": "away_team", "total": "pin_total",
                              "over_price": "pin_over", "under_price": "pin_under"})[
        ["home_team", "away_team", "gameday", "pin_total", "pin_over", "pin_under", "snapshot_utc"]]


def compute(days=8, refresh=True, pinnacle=False):
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
    up["wx_src"] = np.where(closed, "indoor", np.where(up.om_temp.notna(), "era5", "missing"))
    up["wx_wind"] = (cal["wind_intercept"] + cal["wind_slope"] * up.om_wind).clip(lower=0)
    up["wx_temp"] = cal["temp_intercept"] + cal["temp_slope"] * up.om_temp
    up["wx_precip"], up["wx_snow"] = up.om_precip, up.om_snow
    up["indoor"] = closed.astype(int)
    up["roof_open"] = 0
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
    if pinnacle:
        pin = _pinnacle_live()
        if pin is not None and len(pin):
            up = up.merge(pin, on=["home_team", "away_team", "gameday"], how="left")
            has = up.pin_total.notna()
            up.loc[has, ["mkt_total", "mkt_under", "mkt_over"]] = up.loc[has, ["pin_total", "pin_under", "pin_over"]].values
            up.loc[has, "line_src"] = "pinnacle"
    up["p_market"] = market_p_under(up.mkt_under, up.mkt_over, "shin")
    up["edge"] = up.p_under - up.p_market

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
              "mkt_total", "total_line", "spread_line", "pts_effect", "mkt_adjust", "p_under", "p_market", "edge", "lean"]


def save(up):
    """Write output/this_week.csv and append every game (not just leans) to the
    forward-test ledger defined in PREREGISTRATION.md."""
    up[BOARD_COLS].to_csv(OUT / "this_week.csv", index=False)
    path = ROOT / "data" / "forward" / "ledger.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    snap = up[["game_id", "gameday", "gametime", "away_team", "home_team", "lead_days", "wx_src", "wx_wind", "wx_temp",
               "wx_precip", "wx_snow", "line_src", "mkt_total", "mkt_under", "mkt_over", "p_under", "p_market", "lean"]].copy()
    snap = snap.rename(columns={"mkt_total": "total_line", "mkt_under": "under_odds", "mkt_over": "over_odds"})
    snap.insert(0, "snapshot_utc", pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"))
    snap.to_csv(path, mode="a", header=not path.exists(), index=False)
