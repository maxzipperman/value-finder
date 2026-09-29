"""The weather board: forecast weather for upcoming games, the historical scoring
effect of that weather, how much closing totals usually move for it, the model's
P(under), and (when a key is configured) Pinnacle's live total and de-vigged price.
Shared by scripts/this_week.py and scripts/alerts.py."""
from __future__ import annotations

import io
import json
import os
import shutil
from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import fetch
from .build import load_schedule
from .config import OUT, PROC, RAW, ROOT
from .features import BIN_TERMS, LABELS, add_weather_features
from .market import (MIN_UNDER_ODDS, ev_under, fit_under_model, load_games, market_p_under, predict_under,
                     pricing_cohort, valid_odds)
from .models import fit
from .runlog import keep_forecast
from .weather import game_weather, resolve_stadium

# Retractable roofs. With no roof state reported, a game in one of these is treated as closed (indoor);
# a game anywhere else with no roof state is outdoor (amendment 5, section 3). MAD01 is the Bernabeu.
RETRACTABLE = {"ATL97", "DAL00", "HOU00", "IND00", "PHO00", "MAD01"}
RULES_VERSION = "v3-2026-09-28"  # PREREGISTRATION.md amendment 5 (the pricing model; primary and secondary prices)
REGISTERED_VERSIONS = ("v2-2026-09-28", "v3-2026-09-28")   # ledger rows the scorer accepts
PRIMARY_SRC = "pinnacle"         # Rule B's registered price source; any other source is a secondary price
SIGNALS = ("SIGNAL", "SIGNAL_SECONDARY")
PRICING_COHORT_SHA256 = "897a61b6846b077b71c324dc0c2f4b2e28bda963aa69d0cc4a89f181eb039556"   # amendment 5
LAST_UNMAPPED: list[str] = []    # odds-feed team names the last live call couldn't match (for the run record)
LEAN_P = 0.55  # pre-registered (PREREGISTRATION.md)
RULE_B_WIND, RULE_B_LEAD = 15, (1, 3)  # Rule B: forecast wind >= 15 mph, 1-3 days before kickoff
PRICING_LAST_SEASON = 2023             # frozen: pricing cohorts use seasons <= 2023 only


def rule_b_status(r):
    """Why a game is or isn't a Rule B (early wind under) signal; everything else says what's missing.
    "SIGNAL" is priced at Pinnacle and is the registered forward test. "SIGNAL_SECONDARY" passed the
    same gates at the backup price (the nflverse consensus line, used when Pinnacle has no quote); it is
    logged and reported separately, and it is not part of the keep/drop decision (amendment 5)."""
    if r.wx_src != "era5":
        return "not_outdoor"
    if pd.isna(r.wx_wind) or r.wx_wind < RULE_B_WIND:
        return "no_trigger"
    if not (RULE_B_LEAD[0] <= r.lead_days <= RULE_B_LEAD[1]):
        return "outside_horizon"
    if pd.isna(r.mkt_total) or not valid_odds(r.mkt_under):
        return "no_price"
    if r.mkt_under < MIN_UNDER_ODDS:
        return "price_too_high"
    if not (r.ev_under > 0):
        return "negative_ev"
    return "SIGNAL" if getattr(r, "line_src", PRIMARY_SRC) == PRIMARY_SRC else "SIGNAL_SECONDARY"


def wind_components(wind, wind_dir, heading):
    """(crosswind, along-field wind) in mph. `wind_dir` is the direction the wind blows from and
    `heading` is the field's long axis, both in degrees; an axis has no direction, so the angle between
    them runs from 0 (straight down the field) to 90 (straight across). Logged for a later study
    (issue #6); no rule uses it."""
    d = np.abs((np.asarray(wind_dir, float) - np.asarray(heading, float)) % 180)
    angle = np.radians(np.minimum(d, 180 - d))
    wind = np.asarray(wind, float)
    return wind * np.sin(angle), wind * np.cos(angle)


def add_crosswind(up, table=None):
    """Forecast wind direction, crosswind and along-field wind (logging only). Field headings come from
    greerreNFL/stadiums, cross-checked against ThompsonJamesBliss/WeatherData
    (data/processed/stadium_headings.csv; `use` is False where the two disagree). No rule uses these
    columns, so a missing or damaged table leaves them empty and the run goes on."""
    up["wx_wind_dir"] = up.om_wind_dir
    try:
        heads = pd.read_csv(table or PROC / "stadium_headings.csv")
        heads = heads[heads.use.eq(True)].drop_duplicates("stadium_id").set_index("stadium_id").heading
        up["wx_cross"], up["wx_along"] = wind_components(up.wx_wind, up.wx_wind_dir, up.stadium_id.map(heads))
    except Exception as e:
        print(f"  stadium headings unavailable ({type(e).__name__}: {e}); crosswind columns left empty")
        up["wx_cross"], up["wx_along"] = np.nan, np.nan
    return up


def price(up, resid):
    """The pricing model's columns (PREREGISTRATION.md, "the pricing model"). The reference is the rule's
    own total, so the rule's entry is priced at x = 0; a better number at another book is priced at
    x > 0 against that same reference."""
    up["ref_total"] = up.mkt_total
    up["ev_under"] = ev_under(up.mkt_total, up.mkt_under, up.ref_total, resid)
    up["ev_best_line"] = ev_under(up.best_line, up.best_line_under, up.ref_total, resid)
    return up


def under_quotes(totals: pd.DataFrame) -> pd.DataFrame:
    """The feed's complete under quotes: a total and a price that is valid American odds (market.valid_odds).
    A number between -100 and +100 is not a price, so it can't be anyone's best under (as in cfb-weather)."""
    ok = totals.dropna(subset=["total", "under_price"])
    return ok[valid_odds(ok.under_price)]


def best_line(totals: pd.DataFrame, min_odds=MIN_UNDER_ODDS) -> pd.DataFrame:
    """Per event, the highest total any logged book offers the under at, at `min_odds` or better
    (ties go to the better price), with its price and book. Logging only: a higher number than the
    rule book's is where line shopping pays, and the board prices it against the rule book's total."""
    ok = under_quotes(totals)
    ok = ok[ok.under_price >= min_odds]
    best = ok.sort_values(["total", "under_price"], ascending=False).drop_duplicates("event_id")
    return best[["event_id", "total", "under_price", "book"]].rename(
        columns={"total": "best_line", "under_price": "best_line_under", "book": "best_line_book"})


def best_under(totals: pd.DataFrame, rule_book="pinnacle") -> pd.DataFrame:
    """Per event, the best under price any logged book offers at the rule book's total, and
    which book. Logging only (line shopping); Rule B still prices at the rule book. The rule book's
    total counts only when it comes with a valid under price, as in use_pinnacle."""
    ok = under_quotes(totals)
    rule = ok[ok.book == rule_book][["event_id", "total"]]
    same = ok.merge(rule, on=["event_id", "total"])
    best = same.sort_values("under_price", ascending=False).drop_duplicates("event_id")
    return best[["event_id", "under_price", "book"]].rename(columns={"under_price": "best_under",
                                                                    "book": "best_under_book"})


def one_row_per_game(pin: pd.DataFrame) -> pd.DataFrame:
    """One feed row per game (home, away, gameday). The feed can list the same game twice (a relisted
    event); both would join the same schedule row and the board would carry the game twice. Keep the
    event with a complete rule-book quote (a total and a valid under price, as use_pinnacle requires),
    else the first listed."""
    quoted = pin.total.notna() & pin.under_price.map(valid_odds)
    keep = (pin.assign(_quoted=quoted).sort_values("_quoted", ascending=False, kind="stable")
            .drop_duplicates(["home", "away", "gameday"]).index)
    return pin.loc[sorted(keep)]


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
    lost = df[df.home.isna() | df.away.isna()]
    LAST_UNMAPPED[:] = sorted({n for h, a, hn, an in zip(lost.home, lost.away, lost.home_name, lost.away_name)
                               for n, code in ((hn, h), (an, a)) if pd.isna(code)})
    if LAST_UNMAPPED:
        print(f"  odds feed team names with no match (their games arrive unpriced): {LAST_UNMAPPED}")
    # one row per event (then one per game, below), whether or not Pinnacle quotes it, so the best line is
    # logged for every game
    ev = df.dropna(subset=["home", "away"]).drop_duplicates("event_id")[
        ["event_id", "home", "away", "commence_utc", "snapshot_utc"]]
    rule = df[df.book == oddsapi.RULE_BOOK].drop_duplicates("event_id")[
        ["event_id", "total", "over_price", "under_price", "book_update"]]
    pin = (ev.merge(rule, on="event_id", how="left").merge(best_under(df, oddsapi.RULE_BOOK), on="event_id", how="left")
           .merge(best_line(df), on="event_id", how="left"))
    pin["gameday"] = pd.to_datetime(pin.commence_utc, utc=True).dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    pin["snapshot_utc"] = pd.to_datetime(pin.snapshot_utc, utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    pin = one_row_per_game(pin)
    return pin.rename(columns={"home": "home_team", "away": "away_team", "total": "pin_total",
                               "over_price": "pin_over", "under_price": "pin_under", "snapshot_utc": "quote_utc",
                               "book_update": "quote_update"})[
        ["home_team", "away_team", "gameday", "pin_total", "pin_over", "pin_under", "best_under", "best_under_book",
         "best_line", "best_line_under", "best_line_book", "quote_utc", "quote_update"]]


SHOP = {"best_under": np.nan, "best_under_book": "", "best_line": np.nan, "best_line_under": np.nan,
        "best_line_book": "", "quote_utc": "", "quote_update": ""}


def use_pinnacle(up, pin):
    """Price each game at Pinnacle where it has a complete quote (a total and an under price); every
    other game keeps the backup, the nflverse line and prices. The line-shopping columns are filled for
    every game the odds feed lists, whether or not Pinnacle quotes it. `quote_utc` is when the feed was
    read, and `quote_update` is when Pinnacle last updated its market (empty without a Pinnacle quote)."""
    up["line_src"] = "nflverse"
    up["mkt_total"], up["mkt_under"], up["mkt_over"] = up.total_line, up.under_odds, up.over_odds
    if pin is None or not len(pin):
        for c, v in SHOP.items():
            up[c] = v
        return up
    up = up.merge(pin, on=["home_team", "away_team", "gameday"], how="left")
    for c in ("best_under_book", "best_line_book", "quote_utc", "quote_update"):
        up[c] = up[c].fillna("")
    has = up.pin_total.notna() & up.pin_under.map(valid_odds)   # a total without an under price is no quote
    up.loc[has, ["mkt_total", "mkt_under", "mkt_over"]] = up.loc[has, ["pin_total", "pin_under", "pin_over"]].values
    up.loc[has, "line_src"] = PRIMARY_SRC
    return up


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
    # provenance: which forecast file each row used, its content hash and when it was fetched
    up["wx_file"] = [str(RAW / "weather" / "forecast" / f"{resolve_stadium(g.stadium_id, g.stadium)}_{g.gameday}.json")
                     if pd.notna(g.om_temp) else "" for g in up.itertuples(index=False)]
    ident = [keep_forecast(f) for f in up.wx_file]
    up["wx_hash"], up["wx_fetched_utc"] = [i[0] for i in ident], [i[1] for i in ident]
    closed = up.roof.isin(["dome", "closed"]) | (up.roof.isna() & up.stadium_key.isin(RETRACTABLE))
    # open retractable roofs are their own category in training (no weather terms); match that here
    open_roof = up.roof.eq("open") & ~closed
    up["wx_src"] = np.select([closed, open_roof, up.om_temp.notna()], ["indoor", "open_roof", "era5"], "missing")
    up["wx_wind"] = (cal["wind_intercept"] + cal["wind_slope"] * up.om_wind).clip(lower=0)
    up["wx_temp"] = cal["temp_intercept"] + cal["temp_slope"] * up.om_temp
    up["wx_precip"], up["wx_snow"] = up.om_precip, up.om_snow
    # crosswind and along-field wind (logging only): field headings from greerreNFL/stadiums, cross-checked
    # against ThompsonJamesBliss/WeatherData (data/processed/stadium_headings.csv)
    up = add_crosswind(up)
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
    LAST_UNMAPPED[:] = []
    up = use_pinnacle(up, _pinnacle_live() if pinnacle else None)
    up["p_market"] = market_p_under(up.mkt_under, up.mkt_over, "shin")
    up["edge"] = up.p_under - up.p_market

    # The pricing model (amendment 5), from the frozen cohort of outdoor games with 15+ mph wind
    up = price(up, pricing_cohort(PRICING_COHORT_SHA256))
    up["rule_b"] = up.apply(rule_b_status, axis=1)

    # visitor's climate for the acclimation watch: dome status from its latest team-season,
    # and its home city's mean temperature over the last available 7 days (NOAA GHCN-D)
    from .build import FRANCHISE, _practice_temps
    tg = pd.read_parquet(PROC / "team_games.parquet", columns=["team", "franchise", "season", "dome_team", "station"])
    latest = tg.sort_values("season").drop_duplicates("franchise", keep="last")
    try:
        pt = _practice_temps().dropna(subset=["tavg7"]).sort_values("date").drop_duplicates("station", keep="last")
    except (ValueError, OSError) as e:    # no station files: the cold-visitor watch goes without the home-week
        print(f"  practice temperatures unavailable ({type(e).__name__}); cold-visitor watch uses dome status only")
        pt = pd.DataFrame(columns=["station", "tavg7"])    # temperature, and every game is still logged
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
               "ev_under", "rule_b", "best_under", "best_under_book", "ref_total", "best_line", "best_line_under",
               "best_line_book", "ev_best_line", "quote_utc", "quote_update", "wx_hash", "wx_fetched_utc", "wx_wind_dir", "wx_cross", "wx_along"]].copy()
    for f in set(up.get("wx_file", pd.Series(dtype=str)).fillna("")) - {""}:   # keep the forecast behind each row
        keep_forecast(f, ROOT / "data" / "forward" / "forecasts")
    snap = snap.rename(columns={"mkt_total": "total_line", "mkt_under": "under_odds", "mkt_over": "over_odds"})
    snap.insert(0, "snapshot_utc", pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"))
    snap.insert(1, "rules_version", RULES_VERSION)
    if path.exists():  # a ledger written before new columns were added: rewrite once with the union
        if list(pd.read_csv(path, nrows=0).columns) != list(snap.columns):
            return widen_ledger(path, snap)
    snap.to_csv(path, mode="a", header=not path.exists(), index=False)


def widen_ledger(path, snap):
    """Rewrite the ledger once with the union of columns. The old rows are read and written back as
    text, so not one character of them changes; the file before the rewrite is kept beside it, and the
    new file replaces the old one in a single step."""
    old = pd.read_csv(path, dtype=str, keep_default_na=False)
    cols = list(snap.columns) + [c for c in old.columns if c not in snap.columns]
    new = pd.read_csv(io.StringIO(snap.to_csv(index=False)), dtype=str, keep_default_na=False)
    backup = path.with_name(f"{path.stem}.before-{RULES_VERSION}{path.suffix}")
    if not backup.exists():
        shutil.copy2(path, backup)
    tmp = path.with_name(path.name + ".tmp")
    pd.concat([old, new], ignore_index=True).reindex(columns=cols).fillna("").to_csv(tmp, index=False)
    os.replace(tmp, path)
