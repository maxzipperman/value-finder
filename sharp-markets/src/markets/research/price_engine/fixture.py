"""A synthetic F1 fixture: a handful of made-up games written into a scratch cache in the Odds API's featured
format, so the whole backtest runs end to end with no network and no real data. Nothing here is data.

Planted on purpose:
  * NFL game n1: DraftKings' under at Pinnacle's total pays 2.05 (EV +2.5%: flagged at 1% and 2%, not 3%);
    FanDuel's total sits 1.5 points above Pinnacle's at -115 (a soft-book lag flag); Pinnacle's total then
    falls to 44 at the close, so both flags beat the close.
  * NFL game n2: BetMGM's away moneyline beats Pinnacle; Pinnacle moves toward it by the close. FanDuel's over
    pays 2.20 at the close only: a flag first seen at the close is never an entry.
  * CFB game c1 kicks off at 16:00 UTC, the daily snapshot time: that snapshot carries an absurd Caesars price
    that must never become an entry (it is at kickoff), and so does an in-play snapshot after kickoff.
  * CFB game c2: a same-line spread flag at DraftKings.
  * A game in each sealed 2026 season with absurd prices: it must never load.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import yaml

from ...cache import Fetched, RawCache
from ...oddsapi import bulk

UTC = timezone.utc
NOW = datetime(2026, 9, 29, 12, tzinfo=UTC)
CFG = {
    "books": {"us10": ["pinnacle", "lowvig", "betonlineag", "draftkings", "fanduel", "betmgm", "williamhill_us",
                       "fanatics", "betrivers", "espnbet"],
              "sharp3": ["pinnacle", "lowvig", "betonlineag"]},
    "featured": "h2h,spreads,totals",
    "sports": {
        "americanfootball_nfl": {"history_from": "2020-06-06", "sweep_every_days": 2, "windows": [
            {"label": "2024", "from": "2024-09-01", "to": "2025-02-15"},
            {"label": "2026", "from": "2026-09-01", "to": "2027-02-20", "sealed": True}]},
        "americanfootball_ncaaf": {"history_from": "2020-06-06", "sweep_every_days": 2, "windows": [
            {"label": "2024", "from": "2024-08-20", "to": "2025-01-25"},
            {"label": "2026", "from": "2026-08-20", "to": "2027-01-25", "sealed": True}]},
    },
    "pulls": {"F1": {"kind": "featured", "sports": ["americanfootball_nfl", "americanfootball_ncaaf"],
                     "schedule": "daily_close", "books": "us10"}},
}
NFL, CFB = "americanfootball_nfl", "americanfootball_ncaaf"
GAMES = {   # id: (sport, kickoff, home, away, home score, away score)
    "n1": (NFL, "2024-09-08T17:00:00Z", "Kansas City Chiefs", "Baltimore Ravens", 20, 21),
    "n2": (NFL, "2024-09-09T00:20:00Z", "Philadelphia Eagles", "Green Bay Packers", 34, 29),
    "n26": (NFL, "2026-09-13T17:00:00Z", "Buffalo Bills", "New York Jets", 30, 10),
    "c1": (CFB, "2024-09-07T16:00:00Z", "Alabama Crimson Tide", "Wisconsin Badgers", 42, 10),
    "c2": (CFB, "2024-09-07T23:30:00Z", "Texas Longhorns", "Michigan Wolverines", 31, 12),
    "c26": (CFB, "2026-09-12T19:30:00Z", "Ohio State Buckeyes", "Oregon Ducks", 24, 21),
}


def t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def config(tmp) -> dict:
    p = tmp / "odds5m_fixture.yaml"
    p.write_text(yaml.safe_dump(CFG))
    return bulk.load_config(p)


def _book(key, h2h=None, spread=None, total=None):
    """One bookmaker entry. h2h: (home, away) decimal; spread: (home line, home price, away price);
    total: (line, over price, under price)."""
    return key, h2h, spread, total


def prices(gid: str, at: datetime, kick: datetime) -> list[tuple]:
    """Every book's quotes for one game at one snapshot."""
    close = at >= kick - timedelta(minutes=30)
    books = ["pinnacle", "lowvig", "betonlineag", "draftkings", "fanduel", "betmgm", "williamhill_us", "fanatics",
             "betrivers", "espnbet"]
    out = []
    for b in books:
        sharp = b in ("pinnacle", "lowvig", "betonlineag")
        vig = (1.95, 1.95) if sharp else (1.91, 1.91)
        if gid == "n1":
            total = 44.0 if close else 44.5
            h2h = (1.60, 2.45) if sharp else (1.57, 2.40)
            out.append(_book(b, h2h, (-3.0, *vig), (total, *vig)))
        elif gid == "n2":
            h2h = (1.50, 2.75) if not close else (1.55, 2.60)
            if not sharp:
                h2h = (1.47, 2.70)
            if b == "betmgm" and not close:
                h2h = (1.40, 3.10)
            out.append(_book(b, h2h, (-4.5, *vig), (48.5, *vig)))
        elif gid == "c2":
            out.append(_book(b, (1.40, 3.00) if sharp else (1.38, 2.95), (-7.5, *vig), (51.5, *vig)))
        else:                           # c1 and the sealed games: an ordinary market
            out.append(_book(b, (1.20, 5.00) if sharp else (1.18, 4.80), (-13.5, *vig), (50.5, *vig)))
    # the planted retail prices
    planted = []
    for b, h2h, spread, total in out:
        if gid == "n1" and b == "draftkings" and not close:
            total = (44.5, 1.80, 2.05)
        if gid == "n1" and b == "fanduel" and not close:
            total = (46.0, 1.95, 1.87)
        if gid == "c2" and b == "draftkings" and not close:
            spread = (-7.5, 2.06, 1.80)
        if gid == "n2" and b == "fanduel" and close:
            total = (48.5, 2.20, 1.70)                               # flagged only at the close: never an entry
        if gid in ("n26", "c26") and b == "draftkings":
            h2h = (9.0, 9.0)                                         # sealed: must never load
        if gid == "c1" and b == "williamhill_us" and at >= kick:
            h2h = (9.0, 9.0)                                         # at or after kickoff: never an entry
        planted.append((b, h2h, spread, total))
    return planted


def body(at: datetime, sport: str) -> dict:
    data = []
    for gid, (sp, kick_s, home, away, *_) in GAMES.items():
        kick = t(kick_s)
        if sp != sport or not (kick - timedelta(days=8) <= at <= kick + timedelta(hours=3)):
            continue
        bms = []
        for b, h2h, spread, total in prices(gid, at, kick):
            mk = [{"key": "h2h", "outcomes": [{"name": home, "price": h2h[0]}, {"name": away, "price": h2h[1]}]},
                  {"key": "spreads", "outcomes": [{"name": home, "price": spread[1], "point": spread[0]},
                                                  {"name": away, "price": spread[2], "point": -spread[0]}]},
                  {"key": "totals", "outcomes": [{"name": "Over", "price": total[1], "point": total[0]},
                                                 {"name": "Under", "price": total[2], "point": total[0]}]}]
            upd = bulk.iso(at - timedelta(minutes=2 if b == "pinnacle" else 1))
            bms.append({"key": b, "last_update": upd, "markets": [{**m, "last_update": upd} for m in mk]})
        data.append({"id": gid, "sport_key": sport, "commence_time": kick_s, "home_team": home, "away_team": away,
                     "bookmakers": bms})
    return {"timestamp": bulk.iso(at), "previous_timestamp": None, "next_timestamp": None, "data": data}


def build(tmp) -> tuple[dict, list, RawCache, pd.DataFrame]:
    """(config, F1 calls, cache, final scores) for the fixture, written under `tmp`."""
    cfg = config(tmp)
    cache = RawCache(tmp / "raw")
    for sport in (NFL, CFB):
        games = [bulk._label(cfg, {"id": gid, "sport": sp, "commence_time": t(k), "home_team": h, "away_team": a,
                                   "first_seen": None})
                 for gid, (sp, k, h, a, *_) in GAMES.items() if sp == sport]
        bulk.save_schedule(cache.raw_dir, sport, games)
    schedules = bulk.load_schedules(cfg, cache.raw_dir)
    calls = bulk.plan_calls(cfg, "F1", schedules, now=NOW)
    # an extra in-play snapshot after c1's kickoff, as a real featured call would list it
    calls.append(bulk.Call("F1", CFB, bulk.SRC_ODDS, f"/historical/sports/{CFB}/odds",
                           bulk._odds_params(CFG["books"]["us10"], CFG["featured"], t("2024-09-07T17:00:00Z")),
                           t("2024-09-07T17:00:00Z"), 30, False, cache_sport=CFB))
    for c in calls:
        cache.get_or_fetch(sport=c.cache_sport, source=c.source, data_date=c.at.date().isoformat(), url=c.url,
                           params=dict(c.params), fetch=lambda c=c: Fetched(200, {}, json.dumps(body(c.at, c.sport))))
    scores = pd.DataFrame([(sp, gid, float(hs), float(as_)) for gid, (sp, _, _, _, hs, as_) in GAMES.items()],
                          columns=["sport", "event_id", "home_score", "away_score"])
    return cfg, calls, cache, scores
