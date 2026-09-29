"""The price-engine backtest (markets.research.price_engine, issues #8 and #53) on synthetic rows. No network."""
import math
import re
import tempfile
from argparse import Namespace
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from markets import devig
from markets.cache import RawCache
from markets.oddsapi import bulk
from markets.research.price_engine import engine, fixture, model, outcomes, quotes
from markets.research.price_engine import run as pe_run

NFL, CFB = model.NFL, model.CFB
PKG = Path(pe_run.__file__).parent


@pytest.fixture(scope="module")
def fx(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("price_engine")
    cfg, calls, cache, scores = fixture.build(tmp)
    return cfg, calls, cache, scores, pe_run.run(cfg, calls, cache, scores=scores)


def bets(res) -> pd.DataFrame:
    return pd.concat([g for g in res["graded"].values() if len(g)], ignore_index=True)


def rows(eid, snap, commence, book="draftkings", market="totals", prices=((44.5, 1.91), (44.5, 1.91)), sport=NFL):
    """bulk.load_rows-style outcome rows for one book's market at one snapshot."""
    names = ("Over", "Under") if market == "totals" else ("H", "A")
    return [{"sport": sport, "pull": "F1", "snapshot_ts": snap, "requested_ts": snap, "odds_event_id": eid,
             "commence_time": commence, "home_team": "H", "away_team": "A", "bookmaker": book, "book_last_update": snap,
             "market_key": market, "market_last_update": snap, "outcome_name": n, "description": None,
             "point": None if market == "h2h" else str(pt), "price_decimal": str(pr), "origin": "historical"}
            for n, (pt, pr) in zip(names, prices)]


# ---------------------------------------------------------------- no entry at or after kickoff
def test_no_entry_at_or_after_kickoff(fx):
    cfg, calls, cache, scores, res = fx
    q, b = res["quotes"], bets(res)
    assert (q.snap < q.kickoff).all() and (b.snap < b.kickoff).all()
    assert res["drops"]["at_or_after_kickoff"] == 60           # c1's snapshot at its 16:00 kickoff and one in play
    c1 = q[q.event_id == "c1"]
    assert len(c1) and not (c1[["dec_a", "dec_b"]] >= 9).any().any()   # the planted in-play price never loads
    assert "c1" not in set(b.event_id)
    # nor is the close an entry: FanDuel's over on n2 pays 2.20 (EV +10%) only at the close
    assert ((q.event_id == "n2") & (q.book == "fanduel") & (q.dec_a == 2.20)).any()
    assert ((b.kickoff - b.snap) > engine.CLOSE_WINDOW).all() and ((b.commence - b.snap) > engine.CLOSE_WINDOW).all()
    assert list(res["graded"]["H1-NFL-totals-pinnacle-ev1%"].event_id) == ["n1"]


def test_entries_come_from_other_games_closes_too(fx):
    """Every F1 snapshot lists every game, so another game's close is an entry snapshot too, not only 16:00."""
    *_, res = fx
    sides = res["quotes"]
    snaps = set(sides[(sides.event_id == "c2") & (sides.kickoff - sides.snap > engine.CLOSE_WINDOW)]
                .snap.dt.strftime("%m-%d %H:%M"))
    assert {"09-07 15:55", "09-07 16:00"} <= snaps               # c1's close and the daily snapshot, same morning


def _moved_later(tmp_path, monkeypatch, moved_to: str | None, listed: str = "2024-09-08T16:30:00Z"):
    """Pinnacle 44.5 at 1.95 / 1.95 and DraftKings' under at 2.10 (EV +5%) in a 16:00 snapshot that lists kickoff
    `listed`; optionally a 16:25 snapshot that lists the kickoff moved to `moved_to`."""
    batch = (rows("e", "2024-09-08T16:00:00Z", listed, book="pinnacle", prices=((44.5, 1.95), (44.5, 1.95)))
             + rows("e", "2024-09-08T16:00:00Z", listed, book="draftkings", prices=((44.5, 1.80), (44.5, 2.10))))
    if moved_to:
        batch += rows("e", "2024-09-08T16:25:00Z", moved_to, book="pinnacle", prices=((44.5, 1.95), (44.5, 1.95)))
    monkeypatch.setattr(quotes.bulk, "load_rows", lambda cfg, calls, cache: batch)
    q, _ = quotes.load_quotes(fixture.config(tmp_path), [object()], None)
    return engine.entries(engine.side_rows(q, engine.fair_table(q)), engine.Variant("H1", NFL, "totals", "pinnacle",
                                                                                     0.02))


def test_a_kickoff_moved_later_never_admits_an_entry(monkeypatch, tmp_path):
    """At 16:00 the game was listed for 16:30, inside the last hour, so 16:00 was no entry then. A later listing of
    20:00 must not make it one (the latest-listed kickoff is known only afterwards)."""
    assert _moved_later(tmp_path, monkeypatch, None).empty
    assert _moved_later(tmp_path, monkeypatch, "2024-09-08T20:00:00Z").empty
    # the control: listed for 20:00 at 16:00 already, the same price is an entry
    e = _moved_later(tmp_path, monkeypatch, None, listed="2024-09-08T20:00:00Z")
    assert list(zip(e.book, e.side, e.dec)) == [("draftkings", "under", 2.10)]


def test_a_kickoff_moved_earlier_drops_the_later_snapshots(monkeypatch, tmp_path):
    """Kickoff moved from 20:00 to 17:00. A 17:10 snapshot that still listed 20:00 was in play: the in-play
    snapshot at 17:30, which lists 17:00, is the latest listing, so 17:10 is dropped even though it is not itself
    after the kickoff it listed."""
    batch = (rows("e", "2024-09-08T16:00:00Z", "2024-09-08T20:00:00Z", book="pinnacle")
             + rows("e", "2024-09-08T16:55:00Z", "2024-09-08T17:00:00Z", book="pinnacle")
             + rows("e", "2024-09-08T17:10:00Z", "2024-09-08T20:00:00Z", book="pinnacle")
             + rows("e", "2024-09-08T17:30:00Z", "2024-09-08T17:00:00Z", book="pinnacle"))
    monkeypatch.setattr(quotes.bulk, "load_rows", lambda cfg, calls, cache: batch)
    q, drops = quotes.load_quotes(fixture.config(tmp_path), [object()], None)
    assert list(q.snap.dt.strftime("%H:%M")) == ["16:00", "16:55"]
    assert (q.kickoff == pd.Timestamp("2024-09-08T17:00:00Z")).all() and drops["at_or_after_kickoff"] == 2


# ---------------------------------------------------------------- sealed rows never load
def test_sealed_rows_never_load(fx):
    cfg, calls, cache, scores, res = fx
    assert res["sealed_calls"] > 0
    assert not {"n26", "c26"} & set(res["quotes"].event_id)
    assert not {"n26", "c26"} & set(bets(res).event_id)
    # the exclusion is doing the work: the sealed games are in the cache, and only include_sealed would load them
    everything = bulk.load_rows(cfg, calls, cache, include_sealed=True)
    assert {"n26", "c26"} <= {r["odds_event_id"] for r in everything}


def test_the_package_never_asks_for_sealed_rows_or_sealed_scores():
    for path in PKG.glob("*.py"):
        assert not re.search(r"include_sealed\s*=\s*True", path.read_text()), path.name
    assert set(outcomes.nfl_games().season) <= set(range(2020, 2026))       # the tables in git hold 2026 games
    assert set(outcomes.cfb_games().season) <= set(range(2020, 2026))


# ---------------------------------------------------------------- de-vig
def test_devig_sums_to_one():
    rng = np.random.default_rng(7)
    p, margin = rng.uniform(0.02, 0.98, 5000), rng.uniform(0.0, 0.30, 5000)     # up to a 30% overround
    ia, ib = p * (1 + margin), (1 - p) * (1 + margin)
    keep = (ia < 1) & (ib < 1)
    a, b = 1 / ia[keep], 1 / ib[keep]
    for sport in model.SPORTS:
        qa, qb = model.shin(a, b, sport), model.shin(b, a, sport)
        assert np.allclose(qa + qb, 1, atol=1e-9)
        assert ((qa > 0) & (qa < 1)).all()
    assert model.shin([1.91], [1.91])[0] == pytest.approx(0.5)
    assert np.isnan(model.shin([1.0], [1.91])[0])               # an unusable price is no price
    assert np.isnan(model.shin([1.05], [1.30])[0])              # a 72% overround is a broken quote, not a market
    # the registered bisection's one gap below ~44% overround: exactly 25%, symmetric. NaN, never a wrong number
    assert np.isnan(model.shin([1.60], [1.60])[0]) and 0.49 < model.shin([1.61], [1.60])[0] < 0.5


def test_blend_is_devig_blend_over_the_books_at_pinnacles_line(fx):
    *_, res = fx
    fair = res["fair"]
    row = fair[(fair.event_id == "n2") & (fair.market == "h2h")].iloc[0]
    q = res["quotes"]
    at = q[(q.event_id == "n2") & (q.market == "h2h") & (q.snap == row.snap) & q.book.isin(quotes.SHARP)]
    per = {r.book: float(model.shin([r.dec_a], [r.dec_b], NFL)[0]) for r in at.itertuples()}
    want = devig.blend(per, engine.blend_weights())[0]
    assert row.blend_q == pytest.approx(want) and row.pin_q == pytest.approx(per["pinnacle"])
    # a sharp book off Pinnacle's line, or with a broken price, carries no weight; with none left, blend = Pinnacle
    one = pd.DataFrame([{"sport": NFL, "event_id": "e", "snap": row.snap, "market": "totals", "book": b, "line": ln,
                         "dec_a": a, "dec_b": 1.95, "upd": pd.NaT}
                        for b, ln, a in (("pinnacle", 44.5, 1.85), ("lowvig", 45.0, 1.95), ("betonlineag", 44.5, 1.0))])
    f = engine.fair_table(one).iloc[0]
    assert f.blend_q == pytest.approx(f.pin_q) and f.n_sharp == 1


# ---------------------------------------------------------------- a flag's EV arithmetic
def test_flag_ev_arithmetic(fx):
    *_, res = fx
    assert model.ev(0.5, 2.05) == pytest.approx(0.025)
    g = res["graded"]
    dk = g["H1-NFL-totals-pinnacle-ev2%"]
    assert list(dk.book) == ["draftkings"] and list(dk.side) == ["under"]
    assert dk.ev_entry.iloc[0] == pytest.approx(0.025)
    assert len(g["H1-NFL-totals-pinnacle-ev1%"]) == 1 and g["H1-NFL-totals-pinnacle-ev3%"].empty    # 2.5% < 3%
    assert g["H1-CFB-spreads-pinnacle-ev3%"].ev_entry.iloc[0] == pytest.approx(0.03)               # at the line: kept
    mgm = g["H1-NFL-h2h-pinnacle-ev2%"].iloc[0]
    q_away = 1 - model.shin([1.50], [2.75], NFL)[0]
    assert (mgm.book, mgm.side, mgm.dec) == ("betmgm", "away", 3.10)
    assert mgm.ev_entry == pytest.approx(q_away * 3.10 - 1)
    # the first flagged snapshot is the entry, not a later one
    assert mgm.snap == res["quotes"][(res["quotes"].event_id == "n2")].snap.min()


def test_totals_at_another_line_use_the_registered_model():
    mod, resid = model.registered(NFL)
    q, ref, line = 0.48, 44.5, 46.0
    w0, u0 = (float(np.atleast_1d(v)[0]) for v in mod.p_under_at(ref, ref, resid))
    wl, ul = (float(np.atleast_1d(v)[0]) for v in mod.p_under_at(line, ref, resid))
    win = q * (1 - u0) + (wl - w0)
    want = win / (1 - ul)                                        # P(under | no push)
    assert model.under_at(q, ref, line, NFL)[0] == pytest.approx(want)
    assert model.under_at(q, ref, ref, NFL)[0] == pytest.approx(q)                  # same line: Pinnacle's own price
    ups = model.under_at(0.5, 44.5, [43.5, 44.0, 44.5, 45.0, 45.5, 47.5], NFL)
    assert (np.diff(ups) > 0).all()                              # a higher total is a better under
    assert model.under_at(0.5, 54.5, 55.5, CFB)[0] != model.under_at(0.5, 54.5, 55.5, NFL)[0]   # each sport's cohort


def test_spreads_at_another_line_are_never_flagged():
    q = pd.DataFrame([{"sport": NFL, "season": "2024", "event_id": "e", "kickoff": pd.Timestamp("2024-09-08T17:00Z"),
                       "home": "H", "away": "A", "snap": pd.Timestamp("2024-09-07T16:00Z"), "book": b,
                       "market": "spreads", "line": ln, "dec_a": a, "dec_b": 1.91, "upd": pd.NaT}
                      for b, ln, a in (("pinnacle", -3.0, 1.95), ("draftkings", -2.5, 3.0), ("fanduel", -3.0, 2.2))])
    s = engine.side_rows(q, engine.fair_table(q))
    assert s[s.book == "draftkings"].ev_pinnacle.isna().all()   # -2.5 against Pinnacle's -3: not compared
    q_home = model.shin([1.95], [1.91], NFL)[0]
    assert s[(s.book == "fanduel") & (s.side == "home")].ev_pinnacle.iloc[0] == pytest.approx(q_home * 2.2 - 1)


# ---------------------------------------------------------------- CLV sign conventions
def test_clv_sign_conventions():
    e = pd.DataFrame({"sport": NFL, "market": ["totals", "totals", "spreads", "spreads", "h2h"],
                      "side": ["under", "over", "home", "away", "home"], "line": [45.0, 45.0, -3.0, -3.0, np.nan],
                      "dec": 2.0})
    close_line = np.array([44.0, 44.0, -4.0, -4.0, np.nan])
    pts = engine.clv_points(e, close_line)
    assert list(pts[:4]) == [1.0, -1.0, 1.0, -1.0] and np.isnan(pts[4])   # toward the bet is positive
    # the close moves toward the under: the under at 45 is worth more than even money, the over less
    p = engine.close_prob(e, close_line, [1.91] * 5, [1.91] * 5)
    assert p[0] > 0.5 > p[1] and p[0] + p[1] == pytest.approx(1)
    # spreads: the home side closes at -4, so home -3 is worth more than even and away +3 less (converted, not NaN)
    assert p[2] > 0.5 > p[3]
    assert p[4] == pytest.approx(0.5)
    # cents: closing no-vig probability minus the break-even of the price taken
    one = pd.DataFrame({"sport": [NFL], "market": ["h2h"], "side": ["away"], "line": [np.nan], "dec": [2.5]})
    q_away = 1 - model.shin([1.55], [2.60], NFL)[0]
    assert 100 * (engine.close_prob(one, [np.nan], [1.55], [2.60])[0] - 1 / 2.5) == pytest.approx(100 * (q_away - 0.4))


def test_graded_clv_in_the_fixture(fx):
    *_, res = fx
    g = res["graded"]
    under = g["H1-NFL-totals-pinnacle-ev2%"].iloc[0]           # under 44.5 at 2.05; Pinnacle closes at 44
    assert under.clv_pin_pts == pytest.approx(0.5) and under.clv_pin_cents > 0
    lag = g["H2-NFL-totals-lag-gap1"].iloc[0]                   # FanDuel's under at 46, 1.5 above Pinnacle's 44.5
    assert (lag.book, lag.side, lag.line, lag.gap) == ("fanduel", "under", 46.0, 1.5)
    assert lag.clv_pin_pts == pytest.approx(2.0) and lag.clv_own_pts == pytest.approx(2.0)
    mgm = g["H1-NFL-h2h-pinnacle-ev2%"].iloc[0]
    assert mgm.clv_pin_cents == pytest.approx(100 * ((1 - model.shin([1.55], [2.60], NFL)[0]) - 1 / 3.10))


def _spread_bets(close_lines: dict[str, float]) -> tuple[pd.DataFrame, dict]:
    """Home -3 at 2.10 at DraftKings with Pinnacle at -3, 1.95 / 1.95 on entry; Pinnacle closes at each game's line
    in `close_lines`, 1.95 / 1.95."""
    k, e, c = (pd.Timestamp(x) for x in ("2024-09-08T17:00Z", "2024-09-07T16:00Z", "2024-09-08T16:55Z"))
    q = []
    for eid, cl in close_lines.items():
        base = dict(sport=NFL, season="2024", event_id=eid, kickoff=k, commence=k, home="H", away="A",
                    market="spreads", upd=pd.NaT)
        q += [dict(base, snap=e, book="pinnacle", line=-3.0, dec_a=1.95, dec_b=1.95),
              dict(base, snap=e, book="draftkings", line=-3.0, dec_a=2.10, dec_b=1.75),
              dict(base, snap=c, book="pinnacle", line=cl, dec_a=1.95, dec_b=1.95),
              dict(base, snap=c, book="draftkings", line=cl, dec_a=1.91, dec_b=1.91)]
    q = pd.DataFrame(q)
    v = engine.Variant("H1", NFL, "spreads", "pinnacle", 0.02)
    scores = pd.DataFrame({"sport": NFL, "event_id": list(close_lines), "home_score": 24.0, "away_score": 20.0})
    g = engine.grade(engine.entries(engine.side_rows(q, engine.fair_table(q)), v), engine.closes(q), scores)
    g = g.assign(season="2024")
    return g.set_index("event_id"), engine.summarize(v, g)


def test_spread_closes_at_another_number_are_graded_not_dropped():
    """Grading only the bets whose Pinnacle close stayed on the bet's number would select on what happened after
    the bet, and drop exactly the stale-Pinnacle case (Pinnacle moving to the retail book's side)."""
    g, row = _spread_bets({"same": -3.0, "away": -2.5, "toward": -3.5})
    assert row["bets"] == row["clv_pin_n"] == 3
    assert (row["clv_pin_same_n"], row["clv_pin_moved_n"]) == (1, 2)
    assert g.loc["same", "clv_pin_cents"] == pytest.approx(100 * (0.5 - 1 / 2.10))
    # Pinnacle moved against the bet (toward the retail book's view): the bet lost value, CLV negative
    assert g.loc["away", "clv_pin_cents"] < 0 and g.loc["away", "clv_pin_pts"] == -0.5
    assert g.loc["toward", "clv_pin_cents"] > g.loc["same", "clv_pin_cents"] and g.loc["toward", "clv_pin_pts"] == 0.5
    assert bool(g.loc["away", "pin_moved"]) and not bool(g.loc["same", "pin_moved"])
    assert row["clv_pin_cents"] == pytest.approx(g.clv_pin_cents.mean())
    # stale Pinnacle on every bet: the primary CLV sees it
    _, stale = _spread_bets({"a": -2.5, "b": -2.5, "c": -2.0})
    assert stale["clv_pin_n"] == 3 and stale["clv_pin_cents"] < 0


def test_spread_conversion_moves_only_the_mass_between_the_numbers():
    for sport in model.SPORTS:
        assert model.cover_at(0.47, -3.0, -3.0, sport)[0] == pytest.approx(0.47)             # same number
        # -2.5 -> -3: the side that won on a 3-point margin now pushes: (q - P(3)) / (1 - P(3))
        m = model._margins_near(sport, -2.5)
        p3 = float((m == 3).mean())
        assert model.cover_at(0.5, -2.5, -3.0, sport)[0] == pytest.approx((0.5 - p3) / (1 - p3))
        ups = model.cover_at(0.5, -3.0, [-4.5, -3.5, -3.0, -2.5, -1.0, 2.0], sport)
        assert (np.diff(ups) > 0).all()                          # fewer points to give is always better
        assert np.isnan(model.cover_at(np.nan, -3.0, -2.5, sport)[0])
    # the NFL's key number: crossing 3 is worth far more than crossing 5
    nfl = model.cover_at(0.5, -2.5, -3.5, NFL)[0], model.cover_at(0.5, -4.5, -5.5, NFL)[0]
    assert 0.5 - nfl[0] > 2 * (0.5 - nfl[1])


def test_spread_margin_table_is_frozen_before_the_backtest_seasons():
    built = model.build_spread_cohort()
    for sport in model.SPORTS:
        s, m = model.spread_cohort(sport)                        # raises unless the file hashes to the declared value
        assert built[sport]["sha256"] == model.SPREAD_COHORT_SHA256[sport]   # and it rebuilds from the tables in git
        assert built[sport]["seasons"][1] < 2020                 # nothing from 2020-25, the backtest seasons
        assert len(s) == 2 * built[sport]["games"] and (np.sort(s) == np.sort(-s)).all()    # both sides counted
    assert (built[NFL]["games"], built[CFB]["games"]) == (5583, 9396)


def test_results_at_the_price_taken():
    e = pd.DataFrame({"market": ["totals", "totals", "totals", "spreads", "spreads", "h2h", "h2h"],
                      "side": ["under", "over", "under", "home", "away", "home", "away"],
                      "line": [44.0, 44.0, 44.5, -3.0, -3.0, np.nan, np.nan],
                      "home_score": [24, 24, 24, 27, 23, 20, 20], "away_score": [20, 20, 21, 24, 21, 20, 17]})
    won, push = engine.result(e)
    assert list(push) == [1, 1, 0, 1, 0, 1, 0]                  # 44 on 44, 27-24 on -3, a tie
    assert list(won) == [0, 0, 0, 0, 1, 0, 0]                  # the away side at +3 of a 23-21 game covers


# ---------------------------------------------------------------- the variant count and the results table
def test_variant_count_printed_equals_rows_in_the_results_table(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))       # the fixture's scratch cache lands in tmp_path
    assert pe_run.main(Namespace(fixture=True, out=str(tmp_path / "out"))) == 0
    printed = int(re.search(r"variants tested: (\d+)", capsys.readouterr().out).group(1))
    results = pd.read_csv(tmp_path / "out" / "results.csv")
    assert printed == len(results) == len(engine.VARIANTS) == 38
    assert results.variant.is_unique
    assert engine.RUNNING_COUNT == engine.PRIOR_COUNT + 38 and engine.ALPHA == pytest.approx(0.05 / engine.RUNNING_COUNT)
    primary = results[results.primary]
    assert len(primary) == 8 and set(primary.threshold[primary.hypothesis == "H1"]) == {0.02}
    report = (tmp_path / "out" / "report.md").read_text()
    assert "SYNTHETIC FIXTURE" in report and "clv_pin_n" in report and "Closes at another number" in report


def test_the_preregistration_states_the_count_and_bar_the_code_enforces():
    """PRIOR_COUNT was set at registration (Sep 29, 2026: 233). Whoever changes it changes the pre-registration, by
    dated amendment, in the same commit, or this fails."""
    prereg = (model.REPO / pe_run.PREREG).read_text()
    assert f"| Running count before it | {engine.PRIOR_COUNT} |" in prereg
    assert f"**{engine.RUNNING_COUNT}, so the bar is p < 0.05 / {engine.RUNNING_COUNT} = {engine.ALPHA:.6f}**" in prereg


def test_blend_weights_are_pinned_in_code():
    """Not read from config/backtest.yaml at run time: that file is shared with the Kalshi pipeline."""
    assert engine.blend_weights() == {"pinnacle": 0.55, "lowvig": 0.30, "betonlineag": 0.15}
    assert "load_backtest_config" not in (PKG / "engine.py").read_text()


def test_empty_data_prints_the_message_and_stops(tmp_path, capsys, monkeypatch):
    cfg = fixture.config(tmp_path)
    monkeypatch.setattr(pe_run.bulk, "load_config", lambda: cfg)
    monkeypatch.setattr(pe_run, "RawCache", lambda: RawCache(tmp_path / "raw"))
    assert pe_run.main(Namespace(fixture=False, out=str(tmp_path / "out"))) == 0
    out = capsys.readouterr().out
    assert "No F1 data yet" in out and "38 variants" in out and "mostly missed" in out
    assert not (tmp_path / "out").exists()
    # schedules saved by the probe, nothing pulled yet
    bulk.save_schedule(tmp_path / "raw", NFL, [bulk._label(cfg, {"id": "g", "sport": NFL, "home_team": "H",
                                                                  "away_team": "A", "first_seen": None,
                                                                  "commence_time": fixture.t("2024-09-08T17:00:00Z")})])
    assert pe_run.main(Namespace(fixture=False, out=str(tmp_path / "out"))) == 0
    assert "0 of F1's 8 planned snapshots are cached" in capsys.readouterr().out


# ---------------------------------------------------------------- the draft decision rule
def _row(**kw):
    base = dict(primary=True, hypothesis="H1", bets=500, clv_pin_n=500, clv_pin_cents=1.5, clv_pin_p=1e-5, roi_hi=0.05,
                clv_pin_wo_top_book=1.2, clv_pin_wo_best_season=1.1, seasons_counted=6, seasons_positive=5,
                clv_pin_fresh_pin=1.0, clv_pin_ev_below_10=1.3, clv_own_cents=0.4)
    return {**base, **kw}


def test_decision_rule():
    assert engine.decide(_row(), blend_clv=1.0) == "act: paper forward test"
    assert engine.decide(_row(), blend_clv=-0.1) == "inconclusive"                   # the blend version disagrees
    assert engine.decide(_row(clv_pin_p=0.001), blend_clv=1.0) == "inconclusive"     # below the nominal bar only
    assert engine.decide(_row(seasons_positive=4), blend_clv=1.0) == "inconclusive"
    assert engine.decide(_row(clv_pin_cents=-0.2), blend_clv=1.0).startswith("kill: CLV at or below zero")
    assert "one book carries it" in engine.decide(_row(clv_pin_wo_top_book=-0.1), blend_clv=1.0)
    assert "one season carries it" in engine.decide(_row(clv_pin_wo_best_season=0.0), blend_clv=1.0)
    assert "significantly negative" in engine.decide(_row(roi_hi=-0.01), blend_clv=1.0)
    assert engine.decide(_row(bets=99), blend_clv=1.0) == "too few bets"
    assert engine.decide(_row(primary=False)) == "reported"
    assert engine.decide(_row(hypothesis="H2")) == "act: paper forward test"        # H2 has no blend version
    # A6, H2 only (#53): the lagging book's own close must also move toward the bet
    assert engine.decide(_row(hypothesis="H2", clv_own_cents=-0.1)) == "inconclusive"
    assert engine.decide(_row(hypothesis="H2", clv_own_cents=math.nan)) == "inconclusive"
    assert engine.decide(_row(clv_own_cents=-0.1), blend_clv=1.0) == "act: paper forward test"   # H1: reported only


def test_clustered_standard_error():
    m, se, n, p = engine.cmean([1, 1, -1, -1, 3, 3], ["a", "a", "b", "b", "c", "c"])
    assert (m, n) == (1.0, 6) and se == pytest.approx(math.sqrt((0 + 16 + 16) * 3 / 2) / 6)
    assert 0 < p < 0.5


# ---------------------------------------------------------------- outcomes and the registered model
def test_outcome_matching(tmp_path):
    nfl = pd.DataFrame({"season": [2020], "day": [pd.Timestamp("2020-09-13").date()], "home_team": ["WAS"],
                        "away_team": ["PHI"], "home_score": [27.0], "away_score": [17.0]})
    cfb = pd.DataFrame({"season": [2024, 2024, 2024],
                        "start_utc": pd.to_datetime(["2024-09-07T16:00Z", "2024-09-07T16:00Z", "2024-09-01T00:00Z"]),
                        "home_team": ["Miami (OH)", "Miami", "Texas A&M"], "away_team": ["Cincinnati", "Florida A&M",
                                                                                        "Notre Dame"],
                        "home_score": [21.0, 56.0, 13.0], "away_score": [24.0, 9.0, 23.0]})
    ev = pd.DataFrame({"sport": [NFL, CFB, CFB, CFB, CFB], "event_id": ["w", "m1", "m2", "tam", "x"],
                       "kickoff": pd.to_datetime(["2020-09-13T17:00Z", "2024-09-07T16:00Z", "2024-09-07T16:00Z",
                                                  "2024-09-01T00:00Z", "2024-09-01T00:00Z"]),
                       "home": ["Washington Football Team", "Miami (OH) RedHawks", "Miami Hurricanes",
                                "Notre Dame Fighting Irish", "Nowhere Nobodies"],
                       "away": ["Philadelphia Eagles", "Cincinnati Bearcats", "Florida A&M Rattlers",
                                "Texas A&M Aggies", "Texas A&M Aggies"]})
    got, why = outcomes.match(ev, nfl=nfl, cfb=cfb, cfb_raw=tmp_path)
    s = got.set_index("event_id")
    assert (s.loc["w", "home_score"], s.loc["m1", "away_score"], s.loc["m2", "home_score"]) == (27, 24, 56)
    assert (s.loc["tam", "home_score"], s.loc["tam", "away_score"]) == (23, 13)   # neutral site, listed the other way
    assert "x" not in s.index and why == Counter({"cfb_team_name_unknown": 1})


def test_registered_cohort_hashes_are_the_boards():
    for sport, (_, folder, sha) in model.REGISTERED.items():
        board = (model.REPO / folder / folder.replace("-", "") / "board.py").read_text()
        assert re.search(r'PRICING_COHORT_SHA256 = "([0-9a-f]{64})"', board).group(1) == sha
        model.registered(sport)                                  # and the committed cohort file hashes to it
