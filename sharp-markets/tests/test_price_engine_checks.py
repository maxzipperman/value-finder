"""The hub's checker's tests of the price-engine claims the outside audit of September 29, 2026 calls sound (A1, A2,
A3, A6, A7, A9) and of its four findings, on made-up input only (brought in from the hub-briefs handoff,
handoff/price-engine/claims/test_pe_mine.py, and pointed at this checkout). Nothing here is data: every price,
kickoff and score is made up, and any "result" the engine prints on it means nothing about betting.

The tests that asserted the defects the checker found (their names began with test_defect or test_observation) are
turned round here to assert the behaviour amendment 1 registers (sharp-markets/docs/PRICE_ENGINE_PREREGISTRATION.md,
"Amendment 1"); each says which item.
"""
import json
import math
import os
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from markets.cache import Fetched, RawCache
from markets.oddsapi import bulk
from markets.research.price_engine import engine, fixture, model, outcomes, quotes
from markets.research.price_engine import run as pe_run

NFL, CFB = model.NFL, model.CFB
T = pd.Timestamp
H1_TOT = engine.Variant("H1", NFL, "totals", "pinnacle", 0.02)
CFBFASTR = model.REPO / "cfb-weather/data/raw/cfbfastr"          # read-only; only on the Mac


# ---------------------------------------------------------------- helpers
def raw(eid, snap, commence, book, market="totals", a=(44.5, 1.95), b=(44.5, 1.95), sport=NFL, home="H",
        away="A", upd=None, req=None):
    """bulk.load_rows-style outcome rows for one book's market at one snapshot."""
    names = ("Over", "Under") if market == "totals" else (home, away)
    pts = (a[0], b[0]) if market != "h2h" else (None, None)
    if market == "spreads":
        pts = (a[0], -a[0])
    return [{"sport": sport, "pull": "F1", "snapshot_ts": snap, "requested_ts": req or snap, "odds_event_id": eid,
             "commence_time": commence, "home_team": home, "away_team": away, "bookmaker": book,
             "book_last_update": upd or snap, "market_key": market, "market_last_update": upd or snap,
             "outcome_name": n, "description": None, "point": None if p is None else str(p), "price_decimal": str(pr),
             "origin": "historical"} for n, p, pr in zip(names, pts, (a[1], b[1]))]


def load(monkeypatch, tmp_path, batches):
    """quotes.load_quotes on outcome rows; `batches` is one list of rows per planned call."""
    monkeypatch.setattr(quotes.bulk, "load_rows", lambda cfg, calls, cache: sum((batches[i] for i in calls), []))
    return quotes.load_quotes(fixture.config(tmp_path), list(range(len(batches))), None)


def bets_of(q, v=H1_TOT):
    return engine.entries(engine.side_rows(q, engine.fair_table(q)), v)


def pin_dk(eid, snap, commence, under=2.10, line=44.5, pin=(1.95, 1.95), **kw):
    """Pinnacle 44.5 at 1.95 / 1.95 and DraftKings' under at `under` (EV +5% at 2.10) at one snapshot."""
    return (raw(eid, snap, commence, "pinnacle", a=(line, pin[0]), b=(line, pin[1]), **kw)
            + raw(eid, snap, commence, "draftkings", a=(line, 1.80), b=(line, under), **kw))


def qrow(eid, snap, book, market, line, a, b, kick="2024-09-08T17:00Z", season="2024", sport=NFL, commence=None,
         home="H", away="A", upd=None):
    k = T(kick)
    return dict(sport=sport, season=season, event_id=eid, kickoff=k, commence=T(commence) if commence else k,
                home=home, away=away, snap=T(snap), book=book, market=market, line=line, dec_a=a, dec_b=b,
                upd=T(upd) if upd else pd.NaT)


def graded(q, v, scores=None):
    e = engine.entries(engine.side_rows(q, engine.fair_table(q)), v)
    scores = scores if scores is not None else pd.DataFrame(columns=["sport", "event_id", "home_score", "away_score"])
    return engine.grade(e, engine.closes(q), scores)


# ================================================================ A1 lookahead
def test_a1_rows_are_timed_by_the_returned_snapshot_not_the_request_or_last_update(tmp_path):
    """Real cache, real load_rows: requested 16:04, the API returned its 16:00 snapshot, the books' last_update is
    16:03, kickoff 17:01. Only the returned time (61 minutes before) makes 16:00 an entry; the request (57) or the
    last_update (58) would not."""
    cfg, cache = fixture.config(tmp_path), RawCache(tmp_path / "raw")
    at, snap, kick = T("2024-09-08T16:04Z").to_pydatetime(), "2024-09-08T16:00:00Z", "2024-09-08T17:01:00Z"
    c = bulk.Call("F1", NFL, bulk.SRC_ODDS, f"/historical/sports/{NFL}/odds",
                  bulk._odds_params(fixture.CFG["books"]["us10"], fixture.CFG["featured"], at), at, 30, False,
                  cache_sport=NFL)
    ev = {"id": "g", "sport_key": NFL, "commence_time": kick, "home_team": "Kansas City Chiefs",
          "away_team": "Baltimore Ravens", "bookmakers": [
              {"key": bk, "last_update": "2024-09-08T16:03:00Z", "markets": [
                  {"key": "totals", "last_update": "2024-09-08T16:03:00Z", "outcomes": [
                      {"name": "Over", "price": 1.95 if bk == "pinnacle" else 1.80, "point": 44.5},
                      {"name": "Under", "price": 1.95 if bk == "pinnacle" else 2.10, "point": 44.5}]}]}
              for bk in ("pinnacle", "draftkings")]}
    body = {"timestamp": snap, "previous_timestamp": None, "next_timestamp": None, "data": [ev]}
    cache.get_or_fetch(sport=NFL, source=c.source, data_date="2024-09-08", url=c.url, params=dict(c.params),
                       fetch=lambda: Fetched(200, {}, json.dumps(body)))
    q, _ = quotes.load_quotes(cfg, [c], cache)
    assert set(q.snap) == {T(snap)}
    b = bets_of(q)
    assert list(zip(b.book, b.side, b.snap)) == [("draftkings", "under", T(snap))]


def test_a1_kickoff_moved_earlier_removes_entries(monkeypatch, tmp_path):
    # 16:00 lists 20:00; 16:30 lists 16:50 (moved earlier). At 16:00 the game was really 50 minutes away.
    b = bets_of(load(monkeypatch, tmp_path, [pin_dk("g", "2024-09-08T16:00Z", "2024-09-08T20:00Z"),
                                              pin_dk("g", "2024-09-08T16:30Z", "2024-09-08T16:50Z")])[0])
    assert b.empty
    # control: without the move, 16:00 is an entry
    b = bets_of(load(monkeypatch, tmp_path, [pin_dk("g", "2024-09-08T16:00Z", "2024-09-08T20:00Z")])[0])
    assert list(b.snap) == [T("2024-09-08T16:00Z")]


def test_a1_kickoff_moved_later_never_admits_the_earlier_snapshot(monkeypatch, tmp_path):
    # 16:00 lists 16:30 (30 minutes away then); 16:25 lists 20:00. The entry is 16:25, never 16:00.
    q, _ = load(monkeypatch, tmp_path, [pin_dk("g", "2024-09-08T16:00Z", "2024-09-08T16:30Z", under=2.30),
                                        pin_dk("g", "2024-09-08T16:25Z", "2024-09-08T20:00Z")])
    b = bets_of(q)
    assert list(b.snap) == [T("2024-09-08T16:25Z")] and list(b.dec) == [2.10]


def test_a1_kickoff_moved_twice(monkeypatch, tmp_path):
    # 16:00 lists 20:00, 16:30 lists 17:00, 16:45 lists 21:00: latest 21:00. 16:00 was 4 hours out when taken
    # and is 5 hours before the latest listing: an entry. 16:30 listed 17:00 (30 minutes): never an entry.
    q, _ = load(monkeypatch, tmp_path, [pin_dk("g", "2024-09-08T16:00Z", "2024-09-08T20:00Z"),
                                        pin_dk("g", "2024-09-08T16:30Z", "2024-09-08T17:00Z", under=2.40),
                                        pin_dk("g", "2024-09-08T16:45Z", "2024-09-08T21:00Z", under=2.40)])
    assert (q.kickoff == T("2024-09-08T21:00Z")).all()
    b = bets_of(q)
    assert list(b.snap) == [T("2024-09-08T16:00Z")] and list(b.dec) == [2.10]
    # and if the first flag is only at 16:30, the bet waits for 16:45
    q, _ = load(monkeypatch, tmp_path, [pin_dk("g", "2024-09-08T16:00Z", "2024-09-08T20:00Z", under=1.91),
                                        pin_dk("g", "2024-09-08T16:30Z", "2024-09-08T17:00Z", under=2.40),
                                        pin_dk("g", "2024-09-08T16:45Z", "2024-09-08T21:00Z", under=2.20)])
    assert list(bets_of(q).snap) == [T("2024-09-08T16:45Z")]


def test_a1_postponed_a_week(monkeypatch, tmp_path):
    # listed for Sunday Sep 8 17:00, postponed to Sunday Sep 15 17:00. A snapshot of Sep 6 is 9 days before the new
    # kickoff: outside the 7-day window, dropped and counted; Sep 9 onwards are ordinary entries.
    q, drops = load(monkeypatch, tmp_path, [pin_dk("g", "2024-09-06T16:00Z", "2024-09-08T17:00Z", under=2.40),
                                            pin_dk("g", "2024-09-09T16:00Z", "2024-09-15T17:00Z")])
    assert drops["more_than_7_days_before_kickoff"] == 2
    assert list(bets_of(q).snap) == [T("2024-09-09T16:00Z")]


def test_a1_entry_needs_more_than_60_minutes_by_both_kickoffs(monkeypatch, tmp_path):
    for snap, want in (("2024-09-08T16:00Z", 0), ("2024-09-08T15:59:59Z", 1)):
        q, _ = load(monkeypatch, tmp_path, [pin_dk("g", snap, "2024-09-08T17:00Z")])
        assert len(bets_of(q)) == want, snap
    # the listed kickoff alone (latest listing is later) still blocks: 16:00 lists 17:00, 16:10 lists 18:00
    q, _ = load(monkeypatch, tmp_path, [pin_dk("g", "2024-09-08T16:00Z", "2024-09-08T17:00Z", under=2.40),
                                        pin_dk("g", "2024-09-08T16:10Z", "2024-09-08T18:00Z", under=1.91)])
    assert bets_of(q).empty


def test_a1_the_fair_price_is_from_the_same_snapshot_only(monkeypatch, tmp_path):
    # DraftKings' under at 2.10 at 16:00 with no Pinnacle quote then; Pinnacle appears at 16:30 (DK now 1.91).
    batches = [raw("g", "2024-09-08T16:00Z", "2024-09-08T20:00Z", "draftkings", a=(44.5, 1.80), b=(44.5, 2.10)),
               pin_dk("g", "2024-09-08T16:30Z", "2024-09-08T20:00Z", under=1.91)]
    assert bets_of(load(monkeypatch, tmp_path, batches)[0]).empty


def test_a1_a_flag_seen_only_at_the_close_is_never_an_entry(monkeypatch, tmp_path):
    q, _ = load(monkeypatch, tmp_path, [pin_dk("g", "2024-09-08T16:00Z", "2024-09-08T20:00Z", under=1.91),
                                        pin_dk("g", "2024-09-08T19:55Z", "2024-09-08T20:00Z", under=2.50)])
    assert bets_of(q).empty


def test_a1_an_event_id_change_leaves_the_bet_without_a_pinnacle_close():
    q = pd.DataFrame([qrow("old", "2024-09-07T16:00Z", "pinnacle", "totals", 44.5, 1.95, 1.95),
                      qrow("old", "2024-09-07T16:00Z", "draftkings", "totals", 44.5, 1.80, 2.10),
                      qrow("new", "2024-09-08T16:55Z", "pinnacle", "totals", 44.0, 1.95, 1.95),
                      qrow("new", "2024-09-08T16:55Z", "draftkings", "totals", 44.0, 1.91, 1.91)])
    # the old id's last quote is 25 hours before kickoff: no close for it
    g = graded(q, H1_TOT).assign(season="2024")
    row = engine.summarize(H1_TOT, g)
    assert row["bets"] == 1 and row["clv_pin_n"] == 0 and list(g.event_id) == ["old"]


# ================================================================ A2 the close
def _close_q(last_pin_snap, kick="2024-09-08T17:00Z"):
    return pd.DataFrame([qrow("g", "2024-09-07T16:00Z", "pinnacle", "totals", 44.5, 1.95, 1.95, kick=kick),
                         qrow("g", "2024-09-07T16:00Z", "draftkings", "totals", 44.5, 1.80, 2.10, kick=kick),
                         qrow("g", last_pin_snap, "pinnacle", "totals", 44.0, 1.95, 1.95, kick=kick)])


def test_a2_the_close_is_the_last_quote_and_only_within_60_minutes():
    for snap, has in (("2024-09-08T16:00Z", True), ("2024-09-08T15:59Z", False), ("2024-09-08T16:59Z", True)):
        cl = engine.closes(_close_q(snap))
        pin = cl[cl.book == "pinnacle"]
        assert (len(pin) == 1) == has, snap
        if has:
            assert pin.c_snap.iloc[0] == T(snap) and pin.c_line.iloc[0] == 44.0
    # a later, older-kickoff quote cannot be the close; DraftKings' last quote (a day out) gives DK no close
    cl = engine.closes(_close_q("2024-09-08T16:55Z"))
    assert set(cl.book) == {"pinnacle"}


def test_a2_the_close_follows_the_latest_listed_kickoff(monkeypatch, tmp_path):
    # moved later, with a snapshot near the new kickoff: the close is that one
    q, _ = load(monkeypatch, tmp_path, [pin_dk("g", "2024-09-07T16:00Z", "2024-09-08T17:00Z"),
                                        pin_dk("g", "2024-09-08T16:55Z", "2024-09-08T17:00Z"),
                                        pin_dk("g", "2024-09-08T19:55Z", "2024-09-08T20:00Z", line=43.5)])
    cl = engine.closes(q)
    assert set(cl.c_snap) == {T("2024-09-08T19:55Z")}
    # moved later with no snapshot near it: no close at all (16:55 is 3 hours 5 minutes before 20:00)
    q, _ = load(monkeypatch, tmp_path, [pin_dk("g", "2024-09-07T16:00Z", "2024-09-08T17:00Z"),
                                        pin_dk("g", "2024-09-08T16:55Z", "2024-09-08T17:00Z"),
                                        raw("g", "2024-09-08T20:30Z", "2024-09-08T20:00Z", "pinnacle")])
    assert engine.closes(q).empty
    # moved earlier: the close is the last snapshot before the new kickoff; later snapshots are dropped
    q, drops = load(monkeypatch, tmp_path, [pin_dk("g", "2024-09-08T16:00Z", "2024-09-08T20:00Z"),
                                            pin_dk("g", "2024-09-08T16:50Z", "2024-09-08T17:00Z", line=44.0),
                                            pin_dk("g", "2024-09-08T17:30Z", "2024-09-08T17:00Z", line=40.0)])
    cl = engine.closes(q)
    assert set(cl.c_snap) == {T("2024-09-08T16:50Z")} and drops["at_or_after_kickoff"] == 2


def test_a2_a_bet_without_a_pinnacle_close_counts_in_bets_not_in_clv_pin_n():
    q = _close_q("2024-09-08T15:00Z")                           # Pinnacle's last quote is 2 hours out
    g = graded(q, H1_TOT).assign(season="2024")
    row = engine.summarize(H1_TOT, g)
    assert (row["bets"], row["clv_pin_n"]) == (1, 0) and math.isnan(row["clv_pin_cents"])
    many = pd.concat([g.assign(event_id=f"g{i}") for i in range(150)], ignore_index=True)
    r = engine.summarize(H1_TOT, many) | {"primary": True}
    assert engine.decide(r, 1.0) == "too few bets"


# ================================================================ A3 the sealed season
def _fixture_run(tmp_path, keep_sealed_games=True, include_sealed=False, monkeypatch=None, unseal=False):
    games = dict(fixture.GAMES)
    if not keep_sealed_games:
        games = {k: v for k, v in games.items() if k not in ("n26", "c26")}
    monkeypatch.setattr(fixture, "GAMES", games)
    if include_sealed:
        real = bulk.load_rows
        monkeypatch.setattr(quotes.bulk, "load_rows", lambda cfg, calls, cache: real(cfg, calls, cache,
                                                                                    include_sealed=True))
    if unseal:          # the second layer too: label no window sealed inside load_quotes
        real_w = bulk.window_for
        monkeypatch.setattr(quotes.bulk, "window_for", lambda cfg, sport, when: (lambda w: w and dict(w, sealed=False))(
            real_w(cfg, sport, when)))
    tmp_path.mkdir(parents=True, exist_ok=True)
    cfg, calls, cache, scores = fixture.build(tmp_path)
    res = pe_run.run(cfg, calls, cache, scores=scores)
    monkeypatch.undo()
    return res


def _outputs(res):
    bets = pd.concat([g for g in res["graded"].values() if len(g)], ignore_index=True)
    return {"results.csv": res["results"].to_csv(index=False),
            "dropped.csv": pd.DataFrame(sorted(res["drops"].items())).to_csv(index=False),
            "bets.parquet": bets.drop(columns=[]).to_csv(index=False),
            "calibration": res["calibration"].to_csv(index=False), "lag": res["lag"].to_csv(index=False),
            "books": res["books"].to_csv(index=False), "comparable": json.dumps(res["comparable"]),
            "quotes": res["quotes"].to_csv(index=False)}


def test_a3_a_sealed_game_leaves_no_trace(tmp_path, monkeypatch):
    with_sealed = _outputs(_fixture_run(tmp_path / "a", True, monkeypatch=monkeypatch))
    without = _outputs(_fixture_run(tmp_path / "b", False, monkeypatch=monkeypatch))
    for name in with_sealed:
        assert with_sealed[name] == without[name], name
        assert "n26" not in with_sealed[name] and "c26" not in with_sealed[name] and "2026" not in with_sealed[name]
    # the check can fail. Layer 1 off (load_rows asked for sealed rows): load_quotes still drops them, and the
    # count shows in dropped.csv as sealed_season
    one = _outputs(_fixture_run(tmp_path / "c", True, include_sealed=True, monkeypatch=monkeypatch))
    assert one["quotes"] == with_sealed["quotes"] and one["dropped.csv"] != with_sealed["dropped.csv"]
    assert "sealed_season" in one["dropped.csv"]
    # both layers off: the 2026 games reach the quotes, the bets and results.csv
    two = _outputs(_fixture_run(tmp_path / "d", True, include_sealed=True, unseal=True, monkeypatch=monkeypatch))
    assert "n26" in two["quotes"] and two["results.csv"] != with_sealed["results.csv"]


def test_a3_a_2026_game_listed_in_an_unsealed_snapshot_is_left_out(tmp_path):
    """A 2025-season call whose snapshot also lists a game dated in the sealed 2026 window."""
    cfg, cache = fixture.config(tmp_path), RawCache(tmp_path / "raw")
    at = T("2024-09-07T16:00Z").to_pydatetime()
    c = bulk.Call("F1", NFL, bulk.SRC_ODDS, f"/historical/sports/{NFL}/odds",
                  bulk._odds_params(fixture.CFG["books"]["us10"], fixture.CFG["featured"], at), at, 30, False,
                  cache_sport=NFL)
    body = fixture.body(at, NFL)
    ev = json.loads(json.dumps(body["data"][0]))
    ev.update(id="sealed-in-2024-call", commence_time="2026-09-13T17:00:00Z")
    body["data"].append(ev)
    cache.get_or_fetch(sport=NFL, source=c.source, data_date="2024-09-07", url=c.url, params=dict(c.params),
                       fetch=lambda: Fetched(200, {}, json.dumps(body)))
    rows = bulk.load_rows(cfg, [c], cache)
    assert rows and "sealed-in-2024-call" not in {r["odds_event_id"] for r in rows}
    q, drops = quotes.load_quotes(cfg, [c], cache)
    assert "sealed-in-2024-call" not in set(q.event_id) and drops["sealed_season"] == 0


def test_a3_scores_never_return_2026(tmp_path):
    p = tmp_path / "nfl.parquet"
    pd.DataFrame(dict(season=[2024, 2026], gameday=["2024-09-08", "2026-09-13"], home_team=["KC", "KC"],
                      away_team=["BAL", "BAL"], home_score=[20.0, 99.0], away_score=[10.0, 98.0])).to_parquet(p)
    assert list(outcomes.nfl_games(p).season) == [2024]
    c = tmp_path / "cfb.parquet"
    pd.DataFrame(dict(season=[2024, 2026], start_utc=pd.to_datetime(["2024-09-07T19:00Z", "2026-09-12T19:00Z"]),
                      home_team=["Ohio State", "Ohio State"], away_team=["Oregon", "Oregon"], home_points=[20.0, 99.0],
                      away_points=[10.0, 98.0])).to_parquet(c)
    assert list(outcomes.cfb_games(c).season) == [2024]
    ev = pd.DataFrame(dict(sport=[NFL, CFB], event_id=["n26", "c26"],
                           kickoff=pd.to_datetime(["2026-09-13T17:00Z", "2026-09-12T19:00Z"]),
                           home=["Kansas City Chiefs", "Ohio State Buckeyes"], away=["Baltimore Ravens", "Oregon Ducks"]))
    got, why = outcomes.match(ev, nfl=outcomes.nfl_games(p), cfb=outcomes.cfb_games(c), cfb_raw=tmp_path)
    assert got.empty and why == Counter({"nfl_no_game": 1, "cfb_no_game": 1})


def test_a3_observation_the_score_readers_do_read_2026_rows_into_memory(tmp_path, monkeypatch):
    """Not a leak into any output, but the registration's words are 'it never loads 2026 scores'."""
    p = tmp_path / "nfl.parquet"
    pd.DataFrame(dict(season=[2024, 2026], gameday=["2024-09-08", "2026-09-13"], home_team=["KC", "KC"],
                      away_team=["BAL", "BAL"], home_score=[20.0, 99.0], away_score=[10.0, 98.0])).to_parquet(p)
    seen, real = [], pd.read_parquet
    monkeypatch.setattr(pd, "read_parquet", lambda *a, **k: seen.append(real(*a, **k).season.tolist()) or real(*a, **k))
    outcomes.nfl_games(p)
    assert seen == [[2024, 2026]]


# ================================================================ A6 signs and orientation, end to end
# Each game: at the entry snapshot Pinnacle is 1.95 / 1.95 at L0 and DraftKings offers the bet side at 2.10 (the
# other side 1.70, so only the bet side is flagged). At the close Pinnacle has moved toward or away from the bet.
KINDS = {   # kind: (market, side, entry line, close line toward, close line away, h2h close toward, h2h close away)
    "over": ("totals", "over", 44.5, 46.5, 42.5, None, None),
    "under": ("totals", "under", 44.5, 42.5, 46.5, None, None),
    "home_spread": ("spreads", "home", -3.0, -4.5, -1.5, None, None),
    "away_spread": ("spreads", "away", -3.0, -1.5, -4.5, None, None),
    "home_ml": ("h2h", "home", np.nan, np.nan, np.nan, (1.70, 2.25), (2.25, 1.70)),
    "away_ml": ("h2h", "away", np.nan, np.nan, np.nan, (2.25, 1.70), (1.70, 2.25)),
}


def _kind_quotes(kind, direction, sport=NFL):
    mk, side, l0, lt, la, ht_, ha = KINDS[kind]
    a_side = side in ("home", "over")
    dk = (2.10, 1.70) if a_side else (1.70, 2.10)
    close_line = {"toward": lt, "away": la, "same": l0}[direction]
    close_px = (1.95, 1.95) if mk != "h2h" else {"toward": ht_, "away": ha, "same": (1.95, 1.95)}[direction]
    eid = f"{kind}-{direction}"
    rows = [qrow(eid, "2024-09-07T16:00Z", "pinnacle", mk, l0, 1.95, 1.95, sport=sport),
            qrow(eid, "2024-09-07T16:00Z", "draftkings", mk, l0, *dk, sport=sport),
            qrow(eid, "2024-09-08T16:55Z", "pinnacle", mk, close_line, *close_px, sport=sport),
            qrow(eid, "2024-09-08T16:55Z", "draftkings", mk, close_line, *close_px, sport=sport)]
    return rows, engine.Variant("H1", sport, mk, "pinnacle", 0.02)


@pytest.mark.parametrize("sport", [NFL, CFB])
@pytest.mark.parametrize("kind", list(KINDS))
def test_a6_six_kinds_toward_and_away_through_entries_and_grade(kind, sport):
    got = {}
    for direction in ("same", "toward", "away"):
        rows, v = _kind_quotes(kind, direction, sport)
        # final score 24-20: over 44.5 loses (44), under wins, home -3 covers (21 > 20), away +3 loses, home wins
        scores = pd.DataFrame([dict(sport=sport, event_id=f"{kind}-{direction}", home_score=24.0, away_score=20.0)])
        g = graded(pd.DataFrame(rows), v, scores)
        assert len(g) == 1 and g.side.iloc[0] == KINDS[kind][1] and g.dec.iloc[0] == 2.10, (kind, direction)
        got[direction] = g.iloc[0]
    base = got["same"].clv_pin_cents
    assert base == pytest.approx(100 * (0.5 - 1 / 2.10))
    assert got["toward"].clv_pin_cents > base > got["away"].clv_pin_cents, kind
    assert got["toward"].clv_own_cents > base > got["away"].clv_own_cents, kind
    if KINDS[kind][0] != "h2h":
        assert got["toward"].clv_pin_pts > 0 > got["away"].clv_pin_pts and got["same"].clv_pin_pts == 0
        assert bool(got["toward"].pin_moved) and not bool(got["same"].pin_moved)
    else:
        assert np.isnan(got["toward"].clv_pin_pts)
    want_won = {"over": 0, "under": 1, "home_spread": 1, "away_spread": 0, "home_ml": 1, "away_ml": 0}[kind]
    assert got["same"].won == want_won and got["same"].push == 0
    assert got["same"].profit == pytest.approx(1.10 if want_won else -1.0)


def test_a6_pushes():
    e = pd.DataFrame(dict(market=["totals", "totals", "spreads", "spreads", "h2h", "h2h"],
                          side=["over", "under", "home", "away", "home", "away"],
                          line=[44.0, 44.0, -4.0, -4.0, np.nan, np.nan], home_score=24.0, away_score=20.0))
    won, push = engine.result(e)
    assert list(push) == [1, 1, 1, 1, 0, 0] and list(won) == [0, 0, 0, 0, 1, 0]
    e2 = e.assign(home_score=20.0)
    won, push = engine.result(e2)
    assert list(push[4:]) == [1, 1] and list(won[4:]) == [0, 0]


@pytest.mark.parametrize("sport", [NFL, CFB])
def test_a6_feed_home_is_the_score_tables_away_team(sport, tmp_path):
    """The feed lists KC (Georgia) at home; the score table has them as the away team. KC (Georgia) won 27-10."""
    if sport == NFL:
        home, away = "Kansas City Chiefs", "Baltimore Ravens"
        nfl = pd.DataFrame(dict(season=[2024], day=[pd.Timestamp("2024-09-08").date()], home_team=["BAL"],
                                away_team=["KC"], home_score=[10.0], away_score=[27.0]))
        got, why = outcomes.match(pd.DataFrame(dict(sport=[NFL], event_id=["g"], kickoff=[T("2024-09-08T17:00Z")],
                                                     home=[home], away=[away])), nfl=nfl, cfb_raw=tmp_path)
    else:
        home, away = "Georgia Bulldogs", "Alabama Crimson Tide"
        cfb = pd.DataFrame(dict(season=[2024], start_utc=[T("2024-09-08T17:00Z")], home_team=["Alabama"],
                                away_team=["Georgia"], home_score=[10.0], away_score=[27.0]))
        got, why = outcomes.match(pd.DataFrame(dict(sport=[CFB], event_id=["g"], kickoff=[T("2024-09-08T17:00Z")],
                                                     home=[home], away=[away])), cfb=cfb, cfb_raw=tmp_path)
    assert list(zip(got.home_score, got.away_score)) == [(27.0, 10.0)] and not why
    rows = []
    for mk, l0, dk in (("h2h", np.nan, (2.10, 1.70)), ("spreads", -3.0, (2.10, 1.70))):
        rows += [qrow("g", "2024-09-07T16:00Z", "pinnacle", mk, l0, 1.95, 1.95, sport=sport, home=home, away=away),
                 qrow("g", "2024-09-07T16:00Z", "draftkings", mk, l0, *dk, sport=sport, home=home, away=away)]
    q = pd.DataFrame(rows)
    for mk in ("h2h", "spreads"):
        g = graded(q, engine.Variant("H1", sport, mk, "pinnacle", 0.02), got)
        assert list(g.side) == ["home"] and list(g.won) == [1.0] and list(g.profit) == [pytest.approx(1.10)], mk


def test_a6_observation_no_guard_if_the_feed_swaps_home_and_away_between_snapshots():
    """If the feed listed the teams the other way round at the close, the engine would grade against the other
    team's price: nothing checks that `home` is the same at entry and close. Recorded as a risk, not a failure."""
    rows = [qrow("g", "2024-09-07T16:00Z", "pinnacle", "h2h", np.nan, 1.95, 1.95, home="X", away="Y"),
            qrow("g", "2024-09-07T16:00Z", "draftkings", "h2h", np.nan, 2.10, 1.70, home="X", away="Y"),
            # the same close as "home X at 1.70", listed the other way round
            qrow("g", "2024-09-08T16:55Z", "pinnacle", "h2h", np.nan, 2.25, 1.70, home="Y", away="X")]
    g = graded(pd.DataFrame(rows), engine.Variant("H1", NFL, "h2h", "pinnacle", 0.02))
    swapped_right = 100 * (1 - model.shin([2.25], [1.70], NFL)[0] - 1 / 2.10)
    assert g.clv_pin_cents.iloc[0] < 0 < swapped_right        # graded as if the close had moved away from X


# ================================================================ A7 score matching
def test_a7_nfl_matching(tmp_path):
    day = lambda s: pd.Timestamp(s).date()                       # noqa: E731
    nfl = pd.DataFrame(dict(
        season=[2024] * 6,
        day=[day("2024-09-15"), day("2024-12-01"), day("2025-01-11"), day("2024-10-15"), day("2024-11-03"),
             day("2024-11-04")],
        home_team=["KC", "BAL", "KC", "BUF", "PHI", "DAL"], away_team=["BAL", "KC", "BAL", "TEN", "DAL", "PHI"],
        home_score=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0], away_score=[0.0] * 6))
    ev = pd.DataFrame(dict(
        sport=NFL, event_id=["w2", "w13", "wc", "moved", "amb", "unk", "sun_night"],
        kickoff=pd.to_datetime(["2024-09-15T17:00Z", "2024-12-01T21:25Z", "2025-01-11T21:30Z", "2024-10-13T17:00Z",
                                "2024-11-03T18:00Z", "2024-09-15T17:00Z", "2024-12-02T01:20Z"]),
        home=["Kansas City Chiefs", "Baltimore Ravens", "Kansas City Chiefs", "Buffalo Bills", "Philadelphia Eagles",
              "Nowhere Nobodies", "Baltimore Ravens"],
        away=["Baltimore Ravens", "Kansas City Chiefs", "Baltimore Ravens", "Tennessee Titans", "Dallas Cowboys",
              "Kansas City Chiefs", "Kansas City Chiefs"]))
    got, why = outcomes.match(ev, nfl=nfl, cfb_raw=tmp_path)
    s = got.set_index("event_id").home_score.to_dict()
    # three KC-BAL games told apart by date; the Sunday-night 8:20 PM ET game (01:20 UTC Monday) is Sunday's
    assert (s["w2"], s["w13"], s["wc"]) == (1.0, 2.0, 3.0)
    assert s["sun_night"] == 2.0
    assert why == Counter({"nfl_no_game": 1, "nfl_ambiguous": 1, "nfl_team_name_unknown": 1})


def test_a7_cfb_matching(tmp_path):
    cfb = pd.DataFrame(dict(
        season=[2024] * 4,
        start_utc=pd.to_datetime(["2024-09-28T19:30Z", "2024-12-07T20:00Z", "2024-10-05T16:00Z", "2024-10-12T23:00Z"]),
        home_team=["Georgia", "Alabama", "Texas", "Ohio State"], away_team=["Alabama", "Georgia", "Oklahoma", "Oregon"],
        home_score=[1.0, 2.0, 3.0, 4.0], away_score=[0.0] * 4))
    ev = pd.DataFrame(dict(
        sport=CFB, event_id=["reg", "sec_title", "near30h", "far40h", "unk", "same"],
        kickoff=pd.to_datetime(["2024-09-28T19:30Z", "2024-12-07T20:00Z", "2024-10-06T22:00Z", "2024-10-11T07:00Z",
                                "2024-10-12T23:00Z", "2024-10-12T23:00Z"]),
        home=["Georgia Bulldogs", "Georgia Bulldogs", "Texas Longhorns", "Ohio State Buckeyes", "Nowhere Nobodies",
              "Ohio State Buckeyes"],
        away=["Alabama Crimson Tide", "Alabama Crimson Tide", "Oklahoma Sooners", "Oregon Ducks", "Oregon Ducks",
              "Ohio State Buckeyes"]))
    got, why = outcomes.match(ev, cfb=cfb, cfb_raw=tmp_path)
    s = got.set_index("event_id")
    assert (s.loc["reg", "home_score"], s.loc["reg", "away_score"]) == (1.0, 0.0)
    assert (s.loc["sec_title", "home_score"], s.loc["sec_title", "away_score"]) == (0.0, 2.0)   # reoriented
    assert s.loc["near30h", "home_score"] == 3.0
    assert why == Counter({"cfb_no_game": 1, "cfb_team_name_unknown": 2})


# ================================================================ A9 decide() with missing values
def _act_row(**kw):
    base = dict(primary=True, hypothesis="H1", bets=500, clv_pin_n=500, clv_pin_cents=1.5, clv_pin_p=1e-5, roi_hi=0.05,
                clv_pin_wo_top_book=1.2, clv_pin_wo_best_season=1.1, seasons_counted=6, seasons_positive=5,
                clv_pin_fresh_pin=1.0, clv_pin_ev_below_10=1.3, clv_own_cents=0.4)
    return base | kw


FIELDS_EXPECTED = {   # field set to NaN -> the verdict the registration's words imply
    "clv_pin_cents": "kill: CLV at or below zero",
    "clv_pin_wo_top_book": "kill: one book carries it",
    "clv_pin_wo_best_season": "kill: one season carries it",
    "clv_pin_p": "inconclusive",
    "seasons_counted": "inconclusive",
    "seasons_positive": "inconclusive",
    "clv_pin_fresh_pin": "inconclusive",
    "clv_pin_ev_below_10": "inconclusive",
}


@pytest.mark.parametrize("field", list(FIELDS_EXPECTED))
def test_a9_a_missing_value_never_turns_into_act(field):
    assert engine.decide(_act_row(**{field: math.nan}), 1.0) == FIELDS_EXPECTED[field]


def test_a9_the_bar_is_the_corrected_one():
    assert engine.ALPHA == 0.05 / 271
    assert engine.decide(_act_row(clv_pin_p=0.05 / 271 * 1.01), 1.0) == "inconclusive"
    assert engine.decide(_act_row(clv_pin_p=0.05 / 271 * 0.99), 1.0) == "act: paper forward test"


def test_a9_missing_blend_and_own_close():
    assert engine.decide(_act_row(), None) == "inconclusive"
    assert engine.decide(_act_row(), math.nan) == "inconclusive"
    assert engine.decide(_act_row(hypothesis="H2", clv_own_cents=math.nan)) == "inconclusive"
    assert engine.decide(_act_row(clv_own_cents=math.nan), 1.0) == "act: paper forward test"   # H1: reported only


def test_a9_gap_a_missing_roi_interval_never_kills():
    """K2 needs the ROI interval. With no matched scores it is NaN, and the cell can still 'act'. The registration
    keeps unscored games for CLV, so this follows its words, but nothing flags that K2 was never tested."""
    assert engine.decide(_act_row(roi_hi=math.nan), 1.0) == "act: paper forward test"
    # reachable: 150 bets with a Pinnacle close and no final score at all
    k = T("2024-09-08T17:00Z")
    g = pd.DataFrame(dict(event_id=[f"g{i}" for i in range(150)], season=[str(2020 + i % 5) for i in range(150)],
                          book=["draftkings", "fanduel", "betmgm"] * 50, clv_pin_cents=2.0, clv_own_cents=1.0,
                          clv_pin_pts=0.0, clv_own_pts=0.0, pin_moved=False, clv_pin_expected=1.0, ev_entry=0.02,
                          gap=np.nan, hours_before=24.0, pin_stale=False, won=np.nan, push=np.nan, profit=np.nan,
                          kickoff=k))
    g["clv_pin_cents"] = 2.0 + (np.arange(150) % 7) / 10
    row = engine.summarize(H1_TOT, g) | {"primary": True}
    assert row["graded"] == 0 and math.isnan(row["roi_hi"])
    assert engine.decide(row, 1.0) == "act: paper forward test"


def test_a9_unreachable_nan_counts_would_skip_too_few():
    """bets and clv_pin_n are always integers in summarize(); if one were NaN the too-few check would pass."""
    assert engine.decide(_act_row(bets=math.nan), 1.0) == "act: paper forward test"
    assert engine.decide(_act_row(clv_pin_n=math.nan), 1.0) == "act: paper forward test"
    # primary and hypothesis are set by the code from the variant; a NaN would read as primary, and as H1
    assert engine.decide(_act_row(primary=math.nan), 1.0) == "act: paper forward test"
    assert engine.decide(_act_row(hypothesis=math.nan), None) == "inconclusive"


# ================================================================ finding 2: which seasons count for A2
def _cell(seasons):
    """seasons: list of (label, bets, bets with a Pinnacle close, mean CLV of those)."""
    rows, i = [], 0
    for label, n, closed, clv in seasons:
        for j in range(n):
            c = (clv + (j % 3 - 1) * 0.1) if j < closed else np.nan
            rows.append(dict(event_id=f"g{i}", season=label, book=["draftkings", "fanduel", "betmgm"][i % 3],
                             clv_pin_cents=c, clv_own_cents=1.0, clv_pin_pts=0.0, clv_own_pts=0.0, pin_moved=False,
                             clv_pin_expected=1.0, ev_entry=0.02, gap=np.nan, hours_before=24.0, pin_stale=False,
                             won=1.0 if i % 2 else 0.0, push=0.0, profit=1.0 if i % 2 else -1.0))
            i += 1
    g = pd.DataFrame(rows)
    row = engine.summarize(H1_TOT, g) | {"primary": True, "clv_pin_p": 1e-6}     # A1 set to pass: A2 isolated
    return g, row


def _registered_a2(g):
    """The registered sentence: seasons with 20 or more BETS; CLV above zero in all of them but at most one."""
    by = g.groupby("season").agg(bets=("event_id", "size"), clv=("clv_pin_cents", "mean"))
    counted = by[by.bets >= 20]
    return len(counted) >= 3 and int((counted.clv > 0).sum()) >= len(counted) - 1


def test_finding2_code_is_stricter_in_one_direction():
    g, row = _cell([("2020", 50, 50, 2.0), ("2021", 50, 50, 2.0), ("2022", 22, 18, 2.0)])
    assert _registered_a2(g) is True
    assert (row["seasons_counted"], row["seasons_positive"]) == (2, 2)
    assert engine.decide(row, 1.0) == "inconclusive"                # the registered sentence would allow "act"


def test_finding2_code_is_looser_in_the_other_direction():
    """Two seasons with many bets but few Pinnacle closes, both negative: the registered sentence counts them and
    fails A2 (two negative seasons); the code leaves them out and passes."""
    g, row = _cell([("2020", 40, 40, 3.0), ("2021", 40, 40, 3.0), ("2022", 40, 40, 3.0),
                    ("2023", 30, 15, -1.0), ("2024", 30, 15, -1.0)])
    assert _registered_a2(g) is False
    assert (row["seasons_counted"], row["seasons_positive"]) == (3, 3)
    assert row["clv_pin_cents"] > 0 and row["clv_pin_wo_best_season"] > 0 and row["clv_pin_n"] >= 100
    assert engine.decide(row, 1.0) == "act: paper forward test"


# ================================================================ finding 3: prefix school matching
def test_finding3_prefix_matching():
    schools = ["Miami", "Miami (OH)", "Ohio", "Ohio State", "Texas", "Texas A&M"]
    by_len = sorted(((outcomes.norm(s), s) for s in schools), key=lambda x: -len(x[0]))
    assert outcomes._school("Miami RedHawks", {}, by_len) == "Miami"                   # wrong school
    assert outcomes._school("Miami (OH) RedHawks", {}, by_len) == "Miami (OH)"
    assert outcomes._school("Texas A&M Aggies", {}, by_len) == "Texas A&M"
    assert outcomes._school("Ohio Bobcats", {}, by_len) == "Ohio"


@pytest.mark.skipif(not any(CFBFASTR.glob("team_info_*.parquet")), reason="cfbfastR team files not on this machine")
def test_finding3_with_the_real_team_files():
    g = outcomes.cfb_games()
    schools = sorted(set(g.home_team) | set(g.away_team))
    lookup = outcomes.cfb_names(schools, CFBFASTR)
    by_len = sorted(((outcomes.norm(s), s) for s in schools), key=lambda x: -len(x[0]))
    print({n: outcomes._school(n, lookup, by_len) for n in ("Miami RedHawks", "Miami (OH) RedHawks",
                                                             "Miami Hurricanes")})
    assert outcomes._school("Miami (OH) RedHawks", lookup, by_len) == "Miami (OH)"


def test_finding3_a_wrong_school_gives_a_wrong_score_only_if_that_pair_played_within_36_hours(tmp_path):
    cfb = pd.DataFrame(dict(season=[2024], start_utc=[T("2024-09-07T16:00Z")], home_team=["Miami (OH)"],
                            away_team=["Cincinnati"], home_score=[7.0], away_score=[30.0]))
    ev = pd.DataFrame(dict(sport=[CFB], event_id=["e"], kickoff=[T("2024-09-07T16:00Z")], home=["Miami RedHawks"],
                           away=["Cincinnati Bearcats"]))
    got, why = outcomes.match(ev, cfb=pd.concat([cfb, cfb.assign(home_team="Miami", start_utc=T("2024-11-30T17:00Z"))]),
                              cfb_raw=tmp_path)
    assert got.empty and why == Counter({"cfb_no_game": 1})           # misnamed, but logged, not mis-scored


# ================================================================ defect: two calls that return the same snapshot
def _same_snapshot_cache(tmp_path, pad=0):
    """Two F1 requests, 15:55 and 16:00, both answered with the 15:55 snapshot (a 10-minute-era grid at :x5).
    `pad` earlier calls (other snapshots) move the batch boundary."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    cfg, cache = fixture.config(tmp_path), RawCache(tmp_path / "raw")
    calls = []
    kick = "2024-09-07T23:30:00Z"
    def body(ts):
        return {"timestamp": ts, "previous_timestamp": None, "next_timestamp": None, "data": [
            {"id": "g", "sport_key": CFB, "commence_time": kick, "home_team": "Texas Longhorns",
             "away_team": "Michigan Wolverines", "bookmakers": [
                 {"key": bk, "last_update": ts, "markets": [
                     {"key": "totals", "last_update": ts, "outcomes": [
                         {"name": "Over", "price": 1.95 if bk == "pinnacle" else 1.80, "point": 51.5},
                         {"name": "Under", "price": 1.95 if bk == "pinnacle" else 2.10, "point": 51.5}]}]}
                 for bk in ("pinnacle", "draftkings")]}]}
    times = [T("2024-09-07T12:00Z") + pd.Timedelta(minutes=10 * i) for i in range(pad)]
    reqs = [(t, t) for t in times] + [(T("2024-09-07T15:55Z"), T("2024-09-07T15:55Z")),
                                       (T("2024-09-07T16:00Z"), T("2024-09-07T15:55Z"))]
    for req, ts in reqs:
        at = req.to_pydatetime()
        c = bulk.Call("F1", CFB, bulk.SRC_ODDS, f"/historical/sports/{CFB}/odds",
                      bulk._odds_params(fixture.CFG["books"]["us10"], fixture.CFG["featured"], at), at, 30, False,
                      cache_sport=CFB)
        b = json.dumps(body(bulk.iso(ts.to_pydatetime())))
        cache.get_or_fetch(sport=CFB, source=c.source, data_date=at.date().isoformat(), url=c.url,
                           params=dict(c.params), fetch=lambda b=b: Fetched(200, {}, b))
        calls.append(c)
    return cfg, calls, cache


def test_two_calls_returning_one_snapshot_keep_one_copy_and_count_the_other(tmp_path):
    """Amendment 1, item 2 (defect D1, turned round). Before, read in batches of 50, the two copies fell into one
    group of four outcomes and the whole snapshot was dropped as totals_not_two_outcomes."""
    cfg, calls, cache = _same_snapshot_cache(tmp_path)
    q, drops = quotes.load_quotes(cfg, calls, cache)               # as run.run() calls it
    assert len(q) == 2 and drops["duplicate_snapshot"] == 2 and drops["totals_not_two_outcomes"] == 0
    assert drops["duplicate_snapshot_conflicting_price"] == 0
    assert len(bets_of(q, engine.Variant("H1", CFB, "totals", "pinnacle", 0.02))) == 1


def test_the_batch_boundary_no_longer_matters(tmp_path):
    """Amendment 1, item 2 (turned round): wherever the two calls fall in the call list, the snapshot is kept once."""
    kept = {}
    for pad in (0, 49, 99):                    # 49 earlier calls put the pair across calls 49 and 50 of the old batching
        cfg, calls, cache = _same_snapshot_cache(tmp_path / f"p{pad}", pad)
        q, drops = quotes.load_quotes(cfg, calls, cache)
        kept[pad] = (int((q.snap == T("2024-09-07T15:55Z")).sum()), drops["duplicate_snapshot"])
    assert kept == {0: (2, 2), 49: (2, 2), 99: (2, 2)}


# ================================================================ unregistered tie: the book with the most bets
def test_observation_a_tie_for_the_most_bets_is_broken_by_row_order():
    g, _ = _cell([("2020", 40, 40, 1.0), ("2021", 40, 40, 1.0), ("2022", 40, 40, 1.0)])
    g["book"] = ["draftkings"] * 60 + ["fanduel"] * 60
    g["clv_pin_cents"] = [3.0] * 60 + [-1.0] * 60
    a, b = engine.summarize(H1_TOT, g), engine.summarize(H1_TOT, g.iloc[::-1])
    assert (a["top_book"], b["top_book"]) == ("draftkings", "fanduel")
    assert a["clv_pin_wo_top_book"] < 0 < b["clv_pin_wo_top_book"]      # K3 kills one order and not the other


# ================================================================ finding 4: the coarse 9-day cut
def test_finding4_the_coarse_cut_can_drop_a_quote_the_exact_rule_keeps(monkeypatch, tmp_path):
    """Day 0 lists kickoff on day 10 (cut early: more than 7 + 2 days); day 1 lists it on day 5. By the exact rule the
    day-0 quote is 5 days before the latest-listed kickoff and would be kept. It is counted, as 'more than 7 days'."""
    q, drops = load(monkeypatch, tmp_path, [pin_dk("g", "2024-09-01T16:00Z", "2024-09-11T17:00Z"),
                                            pin_dk("g", "2024-09-02T16:00Z", "2024-09-06T17:00Z", under=1.91)])
    assert set(q.snap) == {T("2024-09-02T16:00Z")} and drops["more_than_7_days_before_kickoff"] == 2
    assert bets_of(q).empty          # the day-0 flag (EV +5%) would have been the bet
