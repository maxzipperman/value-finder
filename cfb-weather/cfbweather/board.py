"""College football weather board: upcoming FBS games, the kickoff forecast on the
station scale (frozen calibration), the posted total and prices (The Odds API, else
ESPN), and each game's status under the two pre-registered rules (STRATEGY.md):

* Rule B (wind under): same gates as nfl-weather's rule. A signal needs forecast
  wind >= 15 mph 1-3 days out, a posted total, an under price of -115 or better, and
  positive expected value at that line and price under the registered pricing model
  (amendment 3).
* Rule HT (high-total under, amendment 1): a posted total >= the prior season's mean
  closing total + 10, under at -115 or better. Graded at the last quote before kickoff."""
from __future__ import annotations

import io
import json
import os
import shutil
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import fetch
from .build import schedules, venues
from .config import OUT, PROC, RAW, ROOT
from .features import add_weather_features
from .market import MIN_UNDER_ODDS, ev_under, pricing_cohort, valid_odds
from .runlog import keep_forecast
from .weather import summarize_checked

RULES_VERSION = "cfb-v3-2026-09-28"   # PREREGISTRATION.md amendment 3: the pricing model and clarifications
REGISTERED_VERSIONS = ("cfb-v1-2026-09-28", "cfb-v2-2026-09-28", "cfb-v3-2026-09-28")   # rows the scorer accepts
TEST_SEASONS = (2026, 2027)            # both rules' forward tests end with the 2027 season's title game
PRICING_COHORT_SHA256 = "c49a6649c3f86ac1280ed488f675c14859b23073c1aa8e18aab63060b38bff67"   # amendment 3
RUN_TIMES = ((7, 30), (11, 30), (15, 30), (19, 30))   # the alert job's local run times (scripts/install_alerts.sh)
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


def price(up, resid):
    """The pricing model's columns (PREREGISTRATION.md, "the pricing model"). The reference is the rule's
    own total, so the rule's entry is priced at x = 0; a better number at another book is priced at
    x > 0 against that same reference."""
    up["ref_total"] = up.mkt_total
    up["ev_under"] = ev_under(up.mkt_total, up.mkt_under, up.ref_total, resid)
    up["ev_best_line"] = ev_under(up.best_line, up.best_line_under, up.ref_total, resid)
    return up


def wind_dir_at(js, kick_utc):
    """Forecast wind direction at the kickoff hour (degrees the wind blows from), or NaN. Logged so the
    crosswind can be computed later; no rule uses it."""
    try:
        k0 = pd.Timestamp(kick_utc).tz_convert("UTC").tz_localize(None).floor("h").strftime("%Y-%m-%dT%H:%M")
        return float(js["hourly"]["wind_direction_10m"][js["hourly"]["time"].index(k0)])
    except (KeyError, ValueError, TypeError, AttributeError):
        return np.nan


def season_of(ts):
    """A kickoff's season: August through the January title game belong to the year the season began."""
    ts = pd.Timestamp(ts)
    return ts.year if ts.month >= 7 else ts.year - 1


def local_zone():
    """The Mac's own time zone, by name, so the run times follow the clock launchd fires on and a
    daylight-saving change lands on the right hour. Falls back to the current fixed offset."""
    try:
        return ZoneInfo(os.path.realpath("/etc/localtime").split("/zoneinfo/", 1)[1])
    except Exception:       # no zone link on this machine: the offset in force now
        return datetime.now().astimezone().tzinfo


def next_scheduled_run(now_local):
    """The alert job's next run strictly after `now_local` (a naive or aware local timestamp). Each run
    time is a wall-clock time on its date, so the answer is right across a clock change."""
    now_local = pd.Timestamp(now_local)
    tz = now_local.tzinfo
    day = now_local.tz_localize(None).normalize()
    for d in (day, day + pd.Timedelta(days=1)):
        for h, m in RUN_TIMES:
            t = d + pd.Timedelta(hours=h, minutes=m)
            t = t.tz_localize(tz) if tz is not None else t
            if t > now_local:
                return t
    raise AssertionError("unreachable: tomorrow's first run is always later than now")


def is_last_run_before(kick_utc, now_utc=None, tz=None):
    """True when no scheduled alert run falls between now and kickoff, so this run's quote is the last
    scheduled one. Rule HT alerts only then, and that row is the entry the scorer grades unless a later
    manual snapshot is logged (STRATEGY.md). `tz` defaults to the Mac's own zone."""
    now_utc = pd.Timestamp.now(tz="UTC") if now_utc is None else pd.Timestamp(now_utc)
    nxt = next_scheduled_run(now_utc.tz_convert(tz or local_zone()))
    return pd.Timestamp(kick_utc) > now_utc and nxt.tz_convert("UTC") >= pd.Timestamp(kick_utc)


def rule_ht_status(r):
    """Rule HT (high-total under). Only "SIGNAL" counts; it is graded at the game's last
    logged quote before kickoff, so earlier SIGNAL rows are provisional."""
    if pd.isna(r.mkt_total) or not valid_odds(r.mkt_under):
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
    if pd.isna(r.mkt_total) or not valid_odds(r.mkt_under):
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


def one_row_per_game(oa: pd.DataFrame) -> pd.DataFrame:
    """One Odds API row per game (home, away, UTC day). The feed can list the same game twice (a relisted
    event); both would join the same schedule row and the board would carry the game twice. Keep the
    event priced at a rule book, Pinnacle before DraftKings as in fetch.RULE_BOOKS, else the first listed."""
    rank = oa.line_src.map({b: i for i, b in enumerate(fetch.RULE_BOOKS)}).fillna(len(fetch.RULE_BOOKS))
    keep = (oa.assign(_rank=rank).sort_values("_rank", kind="stable")
            .drop_duplicates(["home_team", "away_team", "day"]).index)
    return oa.loc[sorted(keep)]


def compute(days=8, refresh=True, prices=True):
    """`prices`: price at The Odds API when a key is set (1 credit); False (dry runs) uses ESPN only."""
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
        js = fetch.om_forecast(r.lat, r.lon, day) if refresh else None
        checked = summarize_checked(js, r.start_utc)
        w = checked["values"]
        if not w:
            wx.append(dict(game_id=r.game_id, wx_missing_reason=checked["missing_reason"]))
        if w:
            # provenance: the forecast file this row used, its content hash and when it was fetched
            f = RAW / "openmeteo" / "forecast" / f"{r.lat:.3f}_{r.lon:.3f}_{day}.json"
            h, fetched = keep_forecast(f)
            wx.append(dict(game_id=r.game_id, **w, wx_file=str(f), wx_hash=h, wx_fetched_utc=fetched,
                           wx_wind_dir=wind_dir_at(js, r.start_utc), wx_missing_reason=""))
    up = up.merge(pd.DataFrame(wx, columns=["game_id", "om_wind", "om_temp", "om_precip", "om_snow", "om_gust",
                                            "wx_file", "wx_hash", "wx_fetched_utc", "wx_wind_dir", "wx_missing_reason"]),
                  on="game_id", how="left")
    for c in ("wx_file", "wx_hash", "wx_fetched_utc", "wx_missing_reason"):
        up[c] = up[c].fillna("")
    up["wx_src"] = np.select([up.dome, up.lat.isna(), up.tbd, up.om_wind.notna()],
                             ["indoor", "no_venue", "time_tbd", "forecast"], "no_forecast")
    up["wx_wind"] = (cal["wind_intercept"] + cal["wind_slope"] * up.om_wind).clip(lower=0)
    up["wx_temp"] = cal["temp_intercept"] + cal["temp_slope"] * up.om_temp
    up["wx_precip"], up["wx_snow"] = up.om_precip, up.om_snow
    up["indoor"], up["roof_open"] = up.dome.astype(int), 0
    up = add_weather_features(up)

    # prices: The Odds API when a key is set (licensed, Pinnacle first), else ESPN/DraftKings
    names = odds_team_names()
    # prices=False (dry runs) skips The Odds API so it costs no credits
    oa = fetch.odds_api_totals(names) if prices else pd.DataFrame(columns=["home_team", "away_team"])
    oa = oa.dropna(subset=["home_team", "away_team"])
    if len(oa):
        oa["day"] = pd.to_datetime(oa.commence_utc, utc=True).dt.strftime("%Y-%m-%d")
        oa = one_row_per_game(oa)
        up["day"] = up.start_utc.dt.strftime("%Y-%m-%d")
        up = up.merge(oa.drop(columns="commence_utc"), on=["home_team", "away_team", "day"], how="left")
    else:
        up = up.merge(fetch.espn_week_odds(days), on="game_id", how="left")
    for c, v in (("best_under", np.nan), ("best_under_book", ""), ("best_line", np.nan), ("best_line_under", np.nan),
                 ("best_line_book", ""), ("quote_utc", ""), ("quote_update", "")):
        up[c] = up[c].fillna(v) if c in up else v
    # The pricing model (amendment 3), from the frozen cohort of outdoor games with 15+ mph wind
    up = price(up, pricing_cohort(PRICING_COHORT_SHA256))
    up["rule_b"] = up.apply(rule_b_status, axis=1)
    up["ht_threshold"] = pd.to_numeric(up.season).astype(int).map(ht_threshold)
    up["rule_ht"] = np.where(up.start_utc >= HT_FIRST_KICK, up.apply(rule_ht_status, axis=1), "before_window")
    up["kick_et"] = up.start_utc.dt.tz_convert("America/New_York").dt.strftime("%a %m-%d %H:%M")
    return up.sort_values("start_utc")


COLS = ["game_id", "kick_et", "away_team", "home_team", "venue", "lead_days", "wx_src", "wx_wind", "wx_temp",
        "wx_precip", "line_src", "mkt_total", "mkt_under", "mkt_over", "ev_under", "rule_b", "best_under",
        "best_under_book", "ht_threshold", "rule_ht", "ref_total", "best_line", "best_line_under", "best_line_book",
        "ev_best_line", "quote_utc", "quote_update", "wx_hash", "wx_fetched_utc", "wx_wind_dir"]


def save(up):
    up[COLS].to_csv(OUT / "this_week.csv", index=False)
    path = ROOT / "data" / "forward" / "ledger.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    snap = up[COLS + ["start_utc"]].copy()
    for f in set(up.get("wx_file", pd.Series(dtype=str)).fillna("")) - {""}:   # keep the forecast behind each row
        keep_forecast(f, ROOT / "data" / "forward" / "forecasts")
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
