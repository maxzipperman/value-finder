"""Live uses on a paid Odds API plan: the CFB wind-trigger price poller. LOGGING ONLY: it sends no
alert, places no bet and changes nothing about Rule B, Rule HT or their scoring. GET only.

A background logger: its launchd job sets ODDS_QUOTA_KIND=background, so quota.check() refuses it on
the free plan and stops it at the background floor (quota.py). The alerts and close capture keep
their credits.

Every 10 minutes (scripts/poll_triggers.py), for games whose latest ledger row has a Rule B wind
trigger (board.rule_b_status past "no_trigger") and a kickoff within POLL_HORIZON, one live totals
call (1 credit, fetch.LIVE_BOOKS) logs every book's total and prices to data/forward/trigger_polls.csv.
The raw response goes to data/raw/oddsapi/live/ first, as the alerts' calls do.

The log is holdout data. The 2026 CFB season is sealed (owner decision, Sep 28; the window in
sharp-markets/config/odds5m.yaml), so every row for a 2026-season game carries sealed=True, and nothing
analyses those rows until a hypothesis about them is pre-registered.
"""
from __future__ import annotations

import json

import pandas as pd
import requests

SEALED_SEASON = (pd.Timestamp("2026-08-20", tz="UTC"), pd.Timestamp("2027-01-26", tz="UTC"))  # odds5m.yaml CFB "2026"
TRIGGERED = {"outside_horizon", "no_price", "price_too_high", "negative_ev", "SIGNAL"}
POLL_HORIZON = pd.Timedelta(days=4)
MATCH_TOLERANCE = pd.Timedelta(hours=12)


def sealed(kick_utc) -> bool:
    """True for a game in the sealed 2026 season (holdout data)."""
    k = pd.Timestamp(kick_utc)
    k = k.tz_localize("UTC") if k.tzinfo is None else k.tz_convert("UTC")
    return bool(SEALED_SEASON[0] <= k < SEALED_SEASON[1])


def active_triggers(ledger: pd.DataFrame, now: pd.Timestamp) -> pd.DataFrame:
    """Games whose latest ledger row carries a Rule B wind trigger and that kick off within POLL_HORIZON."""
    if ledger.empty or "rule_b" not in ledger:
        return ledger.iloc[0:0]
    L = ledger.dropna(subset=["start_utc"]).copy()
    L["kick_utc"] = pd.to_datetime(L.start_utc, utc=True)
    L = L.sort_values("snapshot_utc").drop_duplicates("game_id", keep="last")
    return L[L.rule_b.isin(TRIGGERED) & (L.kick_utc > now) & (L.kick_utc - now <= POLL_HORIZON)]


def book_rows(events: list[dict], team_names: dict, stamp: str) -> pd.DataFrame:
    """Every book's totals quote: one row per event x book."""
    from .fetch import norm_team
    lookup = {norm_team(k): v for k, v in team_names.items()}
    rows = []
    for ev in events:
        for b in ev.get("bookmakers", []):
            mk = next((m for m in b.get("markets", []) if m["key"] == "totals"), None)
            if not mk:
                continue
            o = {x["name"].lower(): x for x in mk["outcomes"]}
            rows.append(dict(home_team=lookup.get(norm_team(ev["home_team"])),
                             away_team=lookup.get(norm_team(ev["away_team"])), commence_utc=ev["commence_time"],
                             book=b["key"], total=o.get("under", {}).get("point"),
                             under_price=o.get("under", {}).get("price"), over_price=o.get("over", {}).get("price"),
                             book_update=mk.get("last_update"), quote_utc=stamp))
    return pd.DataFrame(rows, columns=["home_team", "away_team", "commence_utc", "book", "total", "under_price",
                                       "over_price", "book_update", "quote_utc"])


def live_totals(team_names: dict) -> pd.DataFrame | str:
    """Every book's live totals (1 credit), or the reason there are none."""
    from . import quota
    from .config import RAW
    from .fetch import LIVE_BOOKS, ODDS_API, session
    from .notify import _env
    key = _env("ODDS_API_KEY")
    if not key:
        return "no ODDS_API_KEY"
    why = quota.check()
    if why:
        return why
    try:
        r = session.get(ODDS_API, params=dict(apiKey=key, bookmakers=",".join(LIVE_BOOKS), markets="totals",
                                              oddsFormat="american", dateFormat="iso"), timeout=60)
    except requests.RequestException as e:
        return f"Odds API unreachable ({type(e).__name__})"
    quota.record(r, "cfb-weather")
    if r.status_code != 200:
        return f"Odds API unavailable ({r.status_code})"
    stamp = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
    dest = RAW / "oddsapi" / "live" / f"{stamp.replace(':', '')}_poll.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"snapshot_utc": stamp, "credits_last": r.headers.get("x-requests-last"),
                                "credits_remaining": r.headers.get("x-requests-remaining"), "data": r.json()}))
    return book_rows(r.json(), team_names, stamp)


LEDGER_KEEP = ["game_id", "home_team", "away_team", "kick_utc", "snapshot_utc", "rule_b", "wx_wind", "lead_days"]


def trigger_rows(active: pd.DataFrame, quotes: pd.DataFrame, poll_utc: str) -> pd.DataFrame:
    """One row per triggered game x book: the book's total and prices at this poll. Only the ledger
    columns the log needs are carried into the match, so a ledger that gains columns (it gained
    quote_utc and quote_update on Sep 28) can't collide with the quotes' own columns."""
    cols = ["poll_utc", "game_id", "kick_utc", "ledger_snapshot_utc", "rule_b", "wx_wind", "lead_days", "book",
            "total", "under_price", "over_price", "book_update", "quote_utc", "sealed"]
    if active.empty or quotes.empty:
        return pd.DataFrame(columns=cols)
    q = quotes.dropna(subset=["home_team", "away_team"]).copy()
    q["commence"] = pd.to_datetime(q.commence_utc, utc=True)
    led = active[LEDGER_KEEP].rename(columns={"snapshot_utc": "ledger_snapshot_utc"})
    m = led.merge(q, on=["home_team", "away_team"], how="inner")
    m = m[(m.commence - m.kick_utc).abs() <= MATCH_TOLERANCE]
    m = m.assign(poll_utc=poll_utc, sealed=m.kick_utc.map(sealed),
                 kick_utc=m.kick_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
    return m[cols].reset_index(drop=True)
