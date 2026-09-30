"""F1 rows -> one row per game, snapshot, book and market, with both sides' prices.

Input: the rows `bulk.load_rows` returns for F1's cached featured snapshots (h2h, spreads, totals at the us10
books). Sealed seasons are left out there by default, and this module never asks for them (include_sealed keeps
its default); any sealed row that still arrived would be dropped and counted here.

Output columns: sport, season, event_id, kickoff, commence, home, away, snap, book, market, line, dec_a, dec_b,
upd.
  side a / side b: home / away for h2h and spreads, over / under for totals.
  line: the home team's spread for spreads, the total for totals, NaN for h2h.
  snap: the Odds API snapshot timestamp (when the price was known; never last_update, which is only a
        staleness check). upd: the book's market last_update.
  commence: the kickoff as listed in that same snapshot: what a bettor at `snap` could see.
  kickoff: the event's commence_time as listed in its latest snapshot, in-play snapshots included (kickoffs
           move). It is known only later, so it may remove a row or an entry but must never admit one: a
           kickoff that later moved LATER would make an early snapshot look further from kickoff than it was
           at the time. Every cut here uses both kickoffs, and engine.entries requires both to be more than 60
           minutes after the snapshot.

No lookahead. A row is kept only if its snapshot is strictly before kickoff (both the latest-listed kickoff and
the kickoff listed in that same snapshot) and no more than 7 days before it (F1's grid; a featured snapshot also
lists games further out, which F1 was not designed to cover). Everything dropped is counted by reason; nothing
is dropped silently.

F1's snapshots are sport-wide: each one lists every game of that sport. So a game is seen at 16:00 UTC on each
of the 7 days before it and, on busy days, also at every other game's close (on a college Saturday that is every
half hour to few hours), not only at its own daily snapshot.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd

from ...oddsapi import bulk
from ...settings import parse_ts
from .model import SPORTS

MARKETS = ("h2h", "spreads", "totals")
SIDES = {"h2h": ("home", "away"), "spreads": ("home", "away"), "totals": ("over", "under")}
SHARP = ("pinnacle", "lowvig", "betonlineag")
RETAIL = ("draftkings", "fanduel", "betmgm", "williamhill_us", "fanatics", "betrivers", "espnbet")   # us10 minus SHARP
WINDOW = bulk.LOOKBACK                                                                              # 7 days
COARSE_MARGIN = timedelta(days=2)       # the early cut in quote_rows; kickoffs rarely move by more
COLUMNS = ["sport", "season", "event_id", "kickoff", "commence", "home", "away", "snap", "book", "market", "line",
           "dec_a", "dec_b", "upd"]


def f1_calls(cfg: dict, cache, now: datetime | None = None) -> list:
    """F1's planned calls from the saved schedules (NFL and CFB). Empty until `markets odds5m probe` has run."""
    schedules = bulk.load_schedules(cfg, cache.raw_dir, sports=[s for s in SPORTS if s in cfg["sports"]])
    return bulk.plan_calls(cfg, "F1", schedules, now=now) if schedules else []


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def _pair(market: str, out: list[dict], home: str, away: str) -> tuple[float, float, float] | str:
    """(line, dec_a, dec_b) for one book's market at one snapshot, or the reason it can't be used."""
    by = {}
    for r in out:
        by.setdefault(r["outcome_name"], r)
    if len(by) != len(out) or len(out) != 2:
        return f"{market}_not_two_outcomes"
    if market == "totals":
        o, u = by.get("Over"), by.get("Under")
        if o is None or u is None:
            return "totals_not_over_under"
        if _f(o["point"]) != _f(u["point"]) or np.isnan(_f(o["point"])):
            return "totals_points_differ"
        line, a, b = _f(o["point"]), _f(o["price_decimal"]), _f(u["price_decimal"])
    else:
        h, w = by.get(home), by.get(away)
        if h is None or w is None:
            return f"{market}_names_not_home_away"
        line = float("nan")
        if market == "spreads":
            line = _f(h["point"])
            if np.isnan(line) or not np.isclose(line, -_f(w["point"])):
                return "spread_points_not_opposite"
        a, b = _f(h["price_decimal"]), _f(w["price_decimal"])
    if not (a > 1 and b > 1):
        return "price_not_above_1"
    return line, a, b


@lru_cache(maxsize=None)
def _ts(value) -> datetime | None:
    return parse_ts(value) if value else None


def quote_rows(rows: list[dict], drops: Counter, latest: dict | None = None) -> list[tuple]:
    """Group one call's outcome rows into two-sided quotes. Quotes at or after the kickoff the snapshot itself
    lists, or more than 9 days before it (F1's 7-day grid plus COARSE_MARGIN), are counted and dropped here to keep
    memory small; load_quotes applies
    the exact rules with the latest-listed kickoff, which `latest` collects from every row, dropped ones too."""
    latest = {} if latest is None else latest
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        if r["market_key"] not in MARKETS:
            drops["market_not_featured"] += 1
            continue
        key = (r["sport"], r["odds_event_id"], r["snapshot_ts"], r["bookmaker"], r["market_key"])
        groups.setdefault(key, []).append(r)
    out = []
    for (sport, eid, snap, book, market), rs in groups.items():
        r0 = rs[0]
        st, ko = _ts(snap), _ts(r0["commence_time"])
        if st is None or ko is None:
            drops["no_snapshot_or_kickoff_time"] += 1
            continue
        if (sport, eid) not in latest or st > latest[(sport, eid)][0]:
            latest[(sport, eid)] = (st, ko)
        if st >= ko:
            drops["at_or_after_kickoff"] += 1
            continue
        if ko - st > WINDOW + COARSE_MARGIN:
            drops["more_than_7_days_before_kickoff"] += 1
            continue
        got = _pair(market, rs, r0["home_team"], r0["away_team"])
        if isinstance(got, str):
            drops[got] += 1
            continue
        out.append((sport, eid, ko, r0["home_team"], r0["away_team"], st, book, market, *got,
                    _ts(r0.get("market_last_update") or r0.get("book_last_update"))))
    return out


def _n_quotes(rows: list[dict]) -> int:
    """How many quotes quote_rows would count for these rows, kept or dropped: one per row of a market that isn't
    featured, one per (game, snapshot, book, market) group otherwise."""
    return (sum(r["market_key"] not in MARKETS for r in rows)
            + len({(r["sport"], r["odds_event_id"], r["snapshot_ts"], r["bookmaker"], r["market_key"])
                   for r in rows if r["market_key"] in MARKETS}))


def load_quotes(cfg: dict, calls: list, cache) -> tuple[pd.DataFrame, Counter]:
    """The quote table for F1's cached calls, and the count of everything left out, by reason.

    F1 is read one call at a time (amendment 1, item 2). Before the 2022 switch to 5-minute snapshots the API kept
    one snapshot every 10 minutes, so two calls can get back the same snapshot. Read together, their rows fell into
    one group of four outcomes and the whole snapshot was dropped as `*_not_two_outcomes`, depending on where the
    batch boundary fell. Now the first call that returns a (sport, snapshot) is read, and EVERY quote of a later
    call that returns the same (sport, snapshot) is counted once, as `duplicate_snapshot`, before any other reason,
    wherever the calls fall; so no quote is counted twice. Its rows still update the latest-listed kickoff (the
    same snapshot lists the same kickoffs). `duplicate_snapshot_conflicting_price` is a sub-count of
    `duplicate_snapshot`, not a further drop: the repeated quotes whose prices differ from the kept copy's."""
    drops: Counter = Counter()
    raw: list[tuple] = []
    repeats: list[tuple] = []
    latest: dict = {}
    seen: set = set()
    for c in calls:
        rows = bulk.load_rows(cfg, [c], cache)          # sealed seasons are left out here
        snaps = {(r["sport"], r["snapshot_ts"]) for r in rows if r["snapshot_ts"]}
        again = snaps & seen
        seen |= snaps
        if again:
            rep = [r for r in rows if (r["sport"], r["snapshot_ts"]) in again]
            rows = [r for r in rows if (r["sport"], r["snapshot_ts"]) not in again]
            drops["duplicate_snapshot"] += _n_quotes(rep)
            repeats += quote_rows(rep, Counter(), latest)        # only to compare prices; counted once, above
        raw += quote_rows(rows, drops, latest)
    cols = ["sport", "event_id", "commence", "home", "away", "snap", "book", "market", "line", "dec_a", "dec_b", "upd"]
    q = pd.DataFrame(raw, columns=cols)
    if q.empty:
        return pd.DataFrame(columns=COLUMNS), drops
    for c in ("commence", "snap", "upd"):
        q[c] = pd.to_datetime(q[c], utc=True, errors="coerce")
    n = len(q)
    q = q.dropna(subset=["snap", "commence"])
    drops["no_snapshot_or_kickoff_time"] += n - len(q)             # none expected: quote_rows parsed both
    key = ["sport", "event_id", "snap", "book", "market"]
    drops["duplicate_snapshot_conflicting_price"] += 0            # always listed in dropped.csv, as before
    if repeats:
        rq = pd.DataFrame(repeats, columns=cols)
        rq["snap"] = pd.to_datetime(rq.snap, utc=True, errors="coerce")
        conflict = rq.merge(q, on=key, suffixes=("", "_first"))
        drops["duplicate_snapshot_conflicting_price"] += int(((conflict.dec_a != conflict.dec_a_first)
                                                              | (conflict.dec_b != conflict.dec_b_first)).sum())
    # a second layer: one row per (event, snapshot, book, market). Repeated snapshots never reach here (above), so
    # this finds none; it would count one only if two different snapshot stamps parsed to the same instant
    dup = q.duplicated(key, keep="first")
    drops["duplicate_snapshot"] += int(dup.sum())
    q = q[~dup]
    # kickoff: as listed in the event's latest snapshot, in-play ones included
    q["kickoff"] = pd.to_datetime([latest[(s, e)][1] for s, e in zip(q.sport, q.event_id)], utc=True)
    late = (q.snap >= q.kickoff) | (q.snap >= q.commence)
    drops["at_or_after_kickoff"] += int(late.sum())
    far = ~late & (q.kickoff - q.snap > WINDOW)
    drops["more_than_7_days_before_kickoff"] += int(far.sum())
    q = q[~late & ~far].copy()
    labels = {}
    for sport, k in q[["sport", "kickoff"]].drop_duplicates().itertuples(index=False):
        w = bulk.window_for(cfg, sport, k.to_pydatetime())
        labels[(sport, k)] = ("" if w is None else w["label"], bool(w and w["sealed"]))
    lab = [labels[(s, k)] for s, k in zip(q.sport, q.kickoff)]
    q["season"] = [s for s, _ in lab]
    sealed = np.array([x for _, x in lab], dtype=bool)
    drops["sealed_season"] += int(sealed.sum())        # load_rows already leaves these out; counted if any slip through
    outside = ~sealed & (q.season == "")
    drops["outside_season_windows"] += int(outside.sum())
    q = q[~sealed & ~outside]
    return q[COLUMNS].reset_index(drop=True), drops
