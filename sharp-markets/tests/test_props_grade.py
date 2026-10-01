"""The props grader (markets.research.props_grade, issue #10) against mocked F3 event-odds answers. No network.

The rule is nfl-weather/PREREGISTRATION_PROPS.md; each test names the section it pins."""
import math
import re
from argparse import Namespace
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import requests

from markets.cache import RawCache
from markets.oddsapi import bulk
from markets.research.props_grade import fixture, grade, lines as L, outcomes, registration, roster, stats
from markets.research.props_grade import run as pg_run

NFL = L.NFL


@pytest.fixture(scope="module")
def fx(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("props_grade")
    f = fixture.build(tmp)
    games = L.schedule(f.cfg, f.cache)
    calls = L.f3_calls(f.cfg, games, now=fixture.NOW)
    loaded = L.load(f.cfg, calls, f.cache, games)
    paths = pg_run.Paths(f.roster, f.games, f.player_week, f.status, f.prereg, check_git=False, out=tmp / "report")
    df, unmatched_games, pw = pg_run.join(loaded.rows, f.book, paths)
    return f, calls, loaded, paths, df, pw


def close_primary(df):
    return df[(df.role == L.CLOSE) & df.market.isin(L.PRIMARY)]


# ---------------------------------------------------------------- 2.5: the de-vig, known answers
def test_power_devig_known_answer():
    """q_over = 0.6 and q_under = 0.8 (decimal 1/0.6 and 1.25): k = 2 solves 0.36 + 0.64 = 1, so the under's
    power-method probability is 0.64. The additive method gives 0.8 - 0.4/2 = 0.6, the multiplicative 0.8/1.4."""
    assert stats.power_k(0.6, 0.8) == pytest.approx(2.0, abs=1e-12)
    assert stats.devig_power(1 / 0.6, 1.25) == pytest.approx(0.64, abs=1e-12)
    assert stats.devig_additive(1 / 0.6, 1.25) == pytest.approx(0.6, abs=1e-12)
    assert stats.devig_multiplicative(1 / 0.6, 1.25) == pytest.approx(0.8 / 1.4, abs=1e-12)


def test_power_devig_even_prices_and_an_arbitrage():
    """Equal prices give 0.5 by every method. A pair whose implied probabilities sum below 1 needs k < 1."""
    for d in (1.91, 1.87, 2.0):
        assert stats.devig_power(d, d) == pytest.approx(0.5, abs=1e-12)
        assert stats.devig_additive(d, d) == pytest.approx(0.5) and stats.devig_multiplicative(d, d) == 0.5
    k = stats.power_k(1 / 2.1, 1 / 2.05)
    assert k < 1 and (1 / 2.1) ** k + (1 / 2.05) ** k == pytest.approx(1, abs=1e-12)
    p = stats.devig_power(1.87, 1.95)                 # the under is the longer price: below 0.5, sums to 1
    q_o, q_u = 1 / 1.87, 1 / 1.95
    k = stats.power_k(q_o, q_u)
    assert p < 0.5 and q_o ** k + p == pytest.approx(1, abs=1e-12)


# ---------------------------------------------------------------- 2.6: the two standard errors
def test_clustered_se_is_the_registered_formula_not_cr1():
    """Five lines in three games. Residuals win - p: game A +0.5 and -0.5 (sum 0), game B +0.4, game C +0.5 and
    +0.6 (sum 1.1). Excess = 1.5/5 = 0.3. Clustered SE = sqrt(3/2 * (0 + 0.16 + 1.21)) / 5, NOT centred on the
    excess (centring would give sqrt(3/2 * 0.62) / 5). Plain SE = sqrt(0.25+0.25+0.24+0.25+0.24) / 5. The p-value
    decides from the larger SE, one-sided."""
    df = pd.DataFrame({"event_id": ["A", "A", "B", "C", "C"], "win": [1, 0, 1, 1, 1],
                       "p_power": [0.5, 0.5, 0.6, 0.5, 0.4], "p_add": 0.5, "p_mult": 0.5, "d_under": 2.0})
    t = stats.excess_test(df)
    se_game = math.sqrt(1.5 * 1.37) / 5
    se_plain = math.sqrt(1.23) / 5
    assert t["excess"] == pytest.approx(0.3)
    assert t["se_game"] == pytest.approx(se_game) and t["se_game"] != pytest.approx(math.sqrt(1.5 * 0.62) / 5)
    assert t["se_plain"] == pytest.approx(se_plain)
    from scipy.stats import norm
    assert t["p"] == pytest.approx(norm.sf(0.3 / max(se_game, se_plain)))
    assert t["p_plain"] == pytest.approx(norm.sf(0.3 / se_plain)) and t["p"] > t["p_plain"]
    assert t["roi"] == pytest.approx((4 * 1.0 - 1) / 5)             # four wins at 2.0, one loss
    one_game = stats.excess_test(df[df.event_id == "A"])
    assert math.isnan(one_game["se_game"]) and math.isnan(one_game["p"])   # one game: no clustered SE, no p


# ---------------------------------------------------------------- 2.4: the main line and the tie rule
def test_main_line_single_two_lines_and_the_tie_rule():
    one = L.main_line([("Over", "55.5", "1.91"), ("Under", "55.5", "1.91")])
    assert one["line"] == 55.5 and one["p_power"] == pytest.approx(0.5) and one["lines_listed"] == 1
    two = L.main_line([("Over", "85.5", "1.91"), ("Under", "85.5", "1.91"), ("Over", "89.5", "1.70"),
                       ("Under", "89.5", "2.15")])
    assert two["line"] == 85.5 and two["lines_listed"] == 2         # the one closest to even
    near = L.main_line([("Over", "49.5", "1.80"), ("Under", "49.5", "2.02"), ("Over", "50.5", "1.95"),
                        ("Under", "50.5", "1.90")])
    assert near["line"] == 50.5
    mirror = [("Over", "49.5", "1.80"), ("Under", "49.5", "2.02"), ("Over", "50.5", "2.02"), ("Under", "50.5", "1.80")]
    assert L.main_line(mirror) == L.TIE                              # equally close: excluded
    assert L.main_line([("Over", "49.5", "1.91"), ("Under", "49.5", "1.91"), ("Over", "50.5", "1.91"),
                        ("Under", "50.5", "1.91")]) == L.TIE


def test_main_line_missing_prices():
    assert L.main_line([("Over", "35.5", "1.91")]) == L.MISSING                       # no under
    assert L.main_line([("Over", "35.5", "1.91"), ("Under", "35.5", None)]) == L.MISSING
    assert L.main_line([("Over", "35.5", "1.0"), ("Under", "35.5", "1.91")]) == L.MISSING   # not above 1
    assert L.main_line([("Over", None, "1.91"), ("Under", None, "1.91")]) == L.MISSING      # no point
    assert L.main_line([("Over", "35.5", "1.91"), ("Under", "35.5", "1.91"), ("Under", "35.5", "1.80")]) == L.MISSING
    # stricter reading: one usable line and one without an under -> the closest-to-even rule can't be applied
    assert L.main_line([("Over", "35.5", "1.91"), ("Under", "35.5", "1.91"), ("Over", "40.5", "2.3")]) == L.MISSING
    same_twice = L.main_line([("Over", "35.5", "1.91"), ("Under", "35.5", "1.91"), ("Under", "35.5", "1.91")])
    assert same_twice["line"] == 35.5                                 # an identical repeat is one price


# ---------------------------------------------------------------- 2.4: the book
def test_book_rule_needs_80_percent_in_each_primary_market():
    rec, rush = L.PRIMARY
    assert L.choose_book({rec: (80, 100), rush: (8, 10)}) == L.PINNACLE
    assert L.choose_book({rec: (80, 100), rush: (79, 100)}) == L.DRAFTKINGS
    assert L.choose_book({rec: (100, 100), rush: (0, 0)}) == L.DRAFTKINGS     # no rushing line: doesn't clear
    assert L.choose_book({rec: (0, 0), rush: (0, 0)}) is None


def test_coverage_counts_f3a_close_player_games_before_matching(fx):
    """Player-games are (event, description) at F3a's close, counted at any us10 book, unmatched names and games
    the schedule can't match included; T-24h and the sealed game are not counted."""
    f, calls, loaded, *_ = fx
    rec, rush = L.PRIMARY
    assert L.coverage(loaded.rows) == {rec: (2, 13), rush: (1, 10)}
    assert L.choose_book(L.coverage(loaded.rows)) == L.DRAFTKINGS == f.book


def test_no_line_at_the_chosen_book_is_never_filled_in(fx):
    *_, df, _ = fx
    ferguson = df[df.description == "Jake Ferguson"]
    assert set(ferguson.status) == {L.NO_LINE} and ferguson.line.isna().all()        # Pinnacle's line is not used
    assert (df[df.status == ""].book == L.DRAFTKINGS).all()


# ---------------------------------------------------------------- 2.7: pushes, voids, matching, every exclusion
def test_push_and_void(fx):
    *_, df, _ = fx
    c = close_primary(df).set_index("description")
    assert c.loc["Mark Andrews", "status"] == L.PUSH and c.loc["Mark Andrews", "y"] == 40.0
    assert c.loc["Rashee Rice", "status"] == L.VOID and c.loc["Rashee Rice", "player_id"] == "00-K2"
    assert pd.isna(c.loc["Rashee Rice", "y"])
    # a row with no carry is graded at 0 yards: the under wins
    assert c.loc["Javonte Williams", "status"] == "" and c.loc["Javonte Williams", "y"] == 0.0
    assert c.loc["Javonte Williams", "win"] == 1.0


def test_unmatched_players(fx):
    *_, df, _ = fx
    c = close_primary(df).set_index("description")
    assert (c.loc["Nobody Known", "status"], c.loc["Nobody Known", "detail"]) == (L.UNMATCHED, roster.NO_PLAYER)
    assert (c.loc["Chris Smith", "status"], c.loc["Chris Smith", "detail"]) == (L.UNMATCHED, roster.SEVERAL)
    assert c.loc["D.J. Moore", "player_id"] == "00-C1" and c.loc["A.J. Brown", "player_id"] == "00-P1"


def test_every_exclusion_counted_by_reason(fx):
    *_, df, _ = fx
    close = Counter(df[df.role == L.CLOSE].status)
    assert close == {"": 14, L.GAME: 3, L.MOVED: 2, L.NO_LINE: 1, L.MISSING: 1, L.TIE: 1, L.UNMATCHED: 2,
                     L.VOID: 1, L.PUSH: 1}
    t = grade.exclusions(df)
    assert t.lines.sum() == (df.status != "").sum()                    # each excluded line counted once
    assert set(t.reason.astype(str)) <= set(L.REASONS)


def test_kickoff_moved_before_the_close_only(fx):
    """f3: nflverse's kickoff (12:00 ET = 16:00 UTC) is before the close requested at 16:55 UTC, so its close lines
    are excluded; its T-24h lines, a day earlier, are graded."""
    *_, df, _ = fx
    f3 = df[df.event_id == "f3"]
    assert set(f3[f3.role == L.CLOSE].status) == {L.MOVED}
    assert set(f3[f3.role == L.T24].status) == {""}


def test_a_snapshot_listing_its_own_kickoff_as_passed_is_excluded():
    """No in-play price: a row whose snapshot is at or after the kickoff it lists itself is excluded (kickoff
    moved), whatever nflverse says."""
    ts = pd.Timestamp
    pl = pd.DataFrame([{"event_id": "e", "label": "2025", "role": L.CLOSE, "kick": ts("2025-09-07T17:00Z"),
                        "commence": ts("2025-09-07T16:50Z"), "snap": ts("2025-09-07T16:50Z"),
                        "requested": ts("2025-09-07T16:50Z"), "home_team": "x", "away_team": "y",
                        "market": L.PRIMARY[0], "description": "A B", "book": L.DRAFTKINGS, "status": "",
                        "line": 10.5, "d_over": 1.91, "d_under": 1.91, "p_power": 0.5, "p_add": 0.5,
                        "p_mult": 0.5, "lines_listed": 1}])
    games = pd.DataFrame([{"event_id": "e", "game_id": "g", "season": 2025, "home": "KC", "away": "BAL",
                           "kick_nflverse": ts("2025-09-07T17:00Z")}])
    names = roster.NameMap(pd.DataFrame([(2025, "KC", "id1", "A B", "A", "A", "B")], columns=roster.COLUMNS))
    pw = pd.DataFrame([{"season": 2025, "season_type": "REG", "game_id": "g", "player_id": "id1",
                        **{c: 5 for c in outcomes.STAT.values()}}])
    assert grade.assign(pl, games, names, pw).status.tolist() == [L.MOVED]
    assert grade.assign(pl.assign(commence=ts("2025-09-07T17:00Z")), games, names, pw).status.tolist() == [""]


# ---------------------------------------------------------------- the fixture season, hand-computed
def test_fixture_season_reproduces_the_hand_computed_excess(fx):
    """12 graded primary close lines, 8 under wins, eleven at 0.5 and Jackson's at 0.64:
    (8 - 5.5 - 0.64) / 12 = 0.155."""
    *_, df, _ = fx
    g = close_primary(df)
    g = g[g.status == ""]
    t = stats.excess_test(g)
    assert (t["n"], t["under_wins"], t["games"]) == (12, 8, 3)
    assert t["excess"] == pytest.approx(fixture.EXCESS) == pytest.approx(0.155)
    assert g.set_index("description").loc["Lamar Jackson", "p_power"] == pytest.approx(0.64, abs=1e-12)
    assert g.set_index("description").loc["Derrick Henry", "line"] == 85.5         # the main of his two lines
    pooled = grade.table(df, L.CLOSE, L.PRIMARY).set_index("scope").loc["pooled"]
    assert pooled.excess == pytest.approx(0.155) and pooled.n == 12


def test_readout_and_gate_by_hand(fx):
    """Same-season medians over each player's three 2025 rows (the 2026 rows, 999 yards, are never read).
    Receiving: line - median = -4.5, 5.5, 10.5, 5.5, 8.5, 10.5 (mean 6, 5 of 6 above); rushing: -4.5, 5.5, 10.5,
    15.5, 5.5, 5.5 (mean 38/6, 5 of 6 above). The pooled excess is positive, so the gate passes."""
    *_, df, pw = fx
    ro = grade.readout(df, grade.season_medians(pw)).set_index("market")
    rec, rush = L.PRIMARY
    assert ro.loc[rec, "mean_line_minus_median"] == pytest.approx(6.0)
    assert ro.loc[rush, "mean_line_minus_median"] == pytest.approx(38 / 6)
    assert ro.loc[rec, "share_above"] == pytest.approx(5 / 6) == ro.loc[rush, "share_above"]
    gate = grade.gate(df, ro.reset_index())
    assert gate["read"] and gate["passes"] and gate["pooled"]["excess"] == pytest.approx(0.155)


def test_gate_fails_on_any_one_condition(fx):
    *_, df, pw = fx
    ro = grade.readout(df, grade.season_medians(pw))
    rec = L.PRIMARY[0]
    half = ro.assign(share_above=np.where(ro.market == rec, 0.5, ro.share_above))       # exactly half: not "more"
    assert not grade.gate(df, half)["passes"]
    flipped = df.assign(win=np.where(df.status == "", 0.0, df.win))                      # every under loses
    assert not grade.gate(flipped, ro)["passes"]
    assert grade.gate(df[df.season != 2025], ro) == {"read": False, "why": "no graded 2025 line in the primary markets"}


def test_secondary_t24_and_line_move(fx):
    """At T-24h every receiving line is a point lower: the move to the close is +1 for each receiving pair, 0 for
    rushing; the set needs a main line at both snapshots and reads no outcome."""
    *_, df, _ = fx
    mv = grade.line_move(df).set_index("scope")
    rec, rush = L.PRIMARY
    assert (mv.loc[rec, "pairs"], mv.loc[rec, "mean_move"], mv.loc[rec, "share_up"]) == (10, 1.0, 1.0)
    assert (mv.loc[rush, "pairs"], mv.loc[rush, "mean_move"], mv.loc[rush, "share_same"]) == (6, 0.0, 1.0)
    t24 = grade.table(df, L.T24, L.PRIMARY).set_index("scope").loc["pooled"]
    assert t24.n == 15                                     # f3's T-24h lines count; its close lines don't


def test_controls_have_no_p_value(fx):
    *_, df, _ = fx
    c = grade.controls(df)
    assert set(c.scope) >= set(L.CONTROLS) and "p" in c.columns
    out = pg_run.results_section(df, {}, pd.DataFrame(columns=["market", "season", "lines", "no_median",
                                                               "mean_line_minus_median", "share_above"]),
                                 registration.Bar(294, "unfilled", None, 294))
    ctl = out[out.index(next(x for x in out if x.startswith("## Controls"))) + 2]
    assert " p " not in f" {ctl} " and "excess" in ctl                # the controls' header row has no p column


# ---------------------------------------------------------------- the seal
def test_sealed_calls_are_never_read(fx, monkeypatch):
    """The fixture's 2026 game is in the cache with absurd prices. Its calls are planned as sealed and never reach
    bulk.load_rows; nothing of it reaches the join."""
    f, calls, *_ = fx
    sealed = [c for c in calls if c.sealed]
    assert len(sealed) == 2 and {c.event_id for c in sealed} == {"s1"}
    assert all(f.cache.lookup(c.cache_sport, c.source, c.key) for c in sealed)       # it is there to be read
    seen, real = [], bulk.load_rows
    monkeypatch.setattr(L.bulk, "load_rows", lambda cfg, cs, cache, **k: seen.extend(cs) or real(cfg, cs, cache, **k))
    loaded = L.load(f.cfg, calls, f.cache, L.schedule(f.cfg, f.cache))
    assert seen and not any(c.sealed for c in seen) and "s1" not in {c.event_id for c in seen}
    assert loaded.sealed_calls == 2 and "s1" not in set(loaded.rows.event_id)
    assert not (loaded.rows.price.astype(float) >= 50).any()


def test_a_sealed_row_that_slips_through_is_refused_before_the_join(fx, monkeypatch):
    """Layer three: a 2026 row returned for an unsealed call (whatever the reason) is refused and counted before
    anything else sees it, by its sealed window and by its NFL season."""
    f, calls, *_ = fx
    open_call = next(c for c in calls if not c.sealed and c.event_id == "f1")
    row = {"snapshot_ts": "2026-09-13T16:50:00Z", "requested_ts": "x", "odds_event_id": "f1",
           "commence_time": "2026-09-13T17:00:00Z", "home_team": "Kansas City Chiefs", "away_team": "Buffalo Bills",
           "bookmaker": "draftkings", "book_last_update": None, "market_key": L.PRIMARY[0], "market_last_update": None,
           "outcome_name": "Under", "description": "Travis Kelce", "point": "5.5", "price_decimal": "50.0",
           "origin": "historical", "sport": NFL, "pull": "F3"}
    monkeypatch.setattr(L.bulk, "load_rows", lambda *a, **k: [row])
    loaded = L.load(f.cfg, [open_call], f.cache, L.schedule(f.cfg, f.cache))
    assert loaded.rows.empty and loaded.refused == {"game in a sealed season window": 1}
    assert L.sealed_reason(f.cfg, pd.Timestamp("2027-03-05T00:00Z").to_pydatetime()) == \
        "NFL season 2026 or later by the game's date"                 # outside every window, still refused
    assert L.sealed_reason(f.cfg, pd.Timestamp("2026-02-08T23:30Z").to_pydatetime()) is None   # 2025's Super Bowl


def test_outcome_and_schedule_reads_filter_2026_as_they_read(fx, monkeypatch):
    """player_week and games.parquet both hold 2026 rows in the fixture (and in the repo). Every read passes the
    season filter to the reader, names its columns (never a score), and receives no 2026 row."""
    f, *_ = fx
    reads, real = [], pd.read_parquet

    def spy(path, *a, **k):
        got = real(path, *a, **k)
        reads.append((Path(path).name, k.get("columns"), k.get("filters"), set(got.season)))
        return got
    monkeypatch.setattr(pd, "read_parquet", spy)
    pw = outcomes.player_week(f.player_week)
    sched = outcomes.nfl_schedule(f.games)
    assert set(pw.season) == {2025} and set(sched.season) == {2025} and not (pw[list(outcomes.STAT.values())] == 999).any().any()
    assert [r[0] for r in reads] == ["player_week.parquet", "games.parquet"]
    assert all(r[2] == outcomes.SEASON_FILTER and r[3] <= set(outcomes.SEASONS) for r in reads)
    assert not any("score" in c or c in ("result", "total") for r in reads for c in r[1])
    assert real(f.player_week).season.max() == 2026 and real(f.games).season.max() == 2026   # the filter did it


def test_the_whole_fixture_run_calls_no_api_and_writes_its_report(fx, monkeypatch, capsys, tmp_path):
    def no_network(*a, **k):
        raise AssertionError("the grader made an HTTP request")
    monkeypatch.setattr(requests.Session, "get", no_network)
    monkeypatch.setattr(requests, "get", no_network)
    f, *_ = fx
    paths = pg_run.Paths(f.roster, f.games, f.player_week, f.status, f.prereg, check_git=False, out=tmp_path)
    assert pg_run.grade_command(f.cfg, f.cache, paths, book_recorded=f.book, list_excluded=True, fixture=True,
                                now=fixture.NOW) == 0
    text = capsys.readouterr().out
    assert "Gate: PASSES" in text and "Every excluded line" in text and "Rashee Rice" in text
    assert "Not read: section 2.9 is read only on 2023-25; graded seasons: 2025" in text
    assert "n_variants_tested: 1" in text and "bar p < 0.05 / " in text
    lines_csv = pd.read_csv(tmp_path / "lines.csv")
    assert len(lines_csv) == len(fx[4]) and (tmp_path / "report.md").exists()


# ---------------------------------------------------------------- nothing to grade yet, and the stop before the note
def test_empty_cache_prints_nothing_to_grade_yet(tmp_path, capsys):
    cfg = fixture.config(tmp_path)
    paths = pg_run.Paths(out=tmp_path / "out")
    assert pg_run.grade_command(cfg, RawCache(tmp_path / "raw"), paths, now=fixture.NOW) == 0
    out = capsys.readouterr().out
    assert out.startswith("No F3 data yet: no NFL schedule has been saved") and "Nothing to grade yet." in out
    games = [bulk._label(cfg, {"id": "f1", "sport": NFL, "commence_time": fixture.t("2025-09-07T17:00:00Z"),
                               "home_team": "A", "away_team": "B", "first_seen": None})]
    bulk.save_schedule(tmp_path / "raw", NFL, games)
    assert pg_run.grade_command(cfg, RawCache(tmp_path / "raw"), paths, now=fixture.NOW) == 0
    assert "0 of F3's 2 planned 2023-25 calls are cached. Nothing to grade yet." in capsys.readouterr().out
    assert not (tmp_path / "out").exists()


def test_the_cli_on_this_checkout(monkeypatch, tmp_path, capsys):
    """`markets props-grade` with an empty data folder (the cloud, or the Mac before F3a): exit 0."""
    from markets import cli
    monkeypatch.setattr(pg_run, "RawCache", lambda: RawCache(tmp_path / "raw"))
    assert cli.main(["props-grade"]) == 0
    assert "Nothing to grade yet." in capsys.readouterr().out


def _no_outcome_reads(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("an outcome, schedule or roster table was read before the book note")
    for mod, name in ((outcomes, "player_week"), (outcomes, "nfl_schedule"), (outcomes, "match_events"),
                      (roster, "load"), (grade, "assign")):
        monkeypatch.setattr(mod, name, boom)


def test_without_the_book_note_nothing_is_joined(fx, monkeypatch, capsys, tmp_path):
    """2.4: the book is recorded in section 8 before any F3a row is joined to an outcome. Without --book-recorded
    the command prints the coverage and the book and stops (exit 0); with the wrong book, or with no note naming
    it, it refuses (exit 1). No outcome, schedule or roster table is read in any of these."""
    f, *_ = fx
    _no_outcome_reads(monkeypatch)
    paths = pg_run.Paths(f.roster, f.games, f.player_week, f.status, f.prereg, check_git=False, out=tmp_path)
    run = lambda book, p=paths: pg_run.grade_command(f.cfg, f.cache, p, book_recorded=book, now=fixture.NOW)  # noqa
    assert run(None) == 0
    out = capsys.readouterr().out
    assert "Pinnacle lists 2 of 13 player-games (15.4%)" in out and "Book: DraftKings" in out
    assert "Stopped before any outcome is read" in out and "--book-recorded draftkings" in out
    assert run("pinnacle") == 1 and "REFUSED: --book-recorded pinnacle" in capsys.readouterr().out
    unnoted = pg_run.Paths(f.roster, f.games, f.player_week, f.status, registration.PREREG, check_git=False,
                           out=tmp_path)
    assert run("draftkings", unnoted) == 1 and "has no dated note naming DraftKings" in capsys.readouterr().out
    assert not list(tmp_path.iterdir())


def test_an_uncommitted_roster_is_refused(fx, monkeypatch, capsys, tmp_path):
    f, *_ = fx
    _no_outcome_reads(monkeypatch)
    paths = pg_run.Paths(f.roster, f.games, f.player_week, f.status, f.prereg, check_git=True, out=tmp_path)
    assert pg_run.grade_command(f.cfg, f.cache, paths, book_recorded="draftkings", now=fixture.NOW) == 1
    assert "REFUSED: the roster" in capsys.readouterr().out
    assert pg_run.roster_committed(Path(bulk.CONFIG))[0]               # a committed, unchanged file passes


def test_section8_reader():
    assert registration.book_noted(registration.PREREG) == set()      # the registration as committed: placeholder
    assert registration.section8(registration.PREREG) == ""


# ---------------------------------------------------------------- the count and the bar
def test_bar_from_status_and_the_header(tmp_path):
    status = tmp_path / "STATUS.md"
    status.write_text("count went (0.05 / 200) then **271** (0.05 / 271), now p < 0.000170 (0.05 / 294).\n")
    prereg = tmp_path / "P.md"
    unfilled = ("- **Count and bar at registration:** *(the hub fills this in: ...)* As of writing, for "
                "illustration: 274 ... = 288, p < 0.05 / 288 = 0.000174\n")
    prereg.write_text(unfilled)
    b = registration.bar(status, prereg)
    assert (b.status_count, b.header, b.header_count, b.count) == (294, "unfilled", None, 294)
    assert b.alpha == pytest.approx(0.05 / 294)
    prereg.write_text("- **Count and bar at registration:** 300 (294 in STATUS.md + 6 run), p < 0.05 / 300\n")
    assert registration.bar(status, prereg).count == 300                          # the larger count
    prereg.write_text("- **Count and bar at registration:** 288, p < 0.05 / 288\n")
    b = registration.bar(status, prereg)
    assert (b.header, b.header_count, b.count) == ("filled", 288, 294)            # STATUS.md's is stricter
    prereg.write_text("- **Count and bar at registration:** two hundred\n")
    assert registration.bar(status, prereg).header == "unreadable"
    assert registration.bar(tmp_path / "none.md", tmp_path / "none.md").count is None


def test_bar_on_this_checkout():
    """STATUS.md's running count today is at least 294; the count used is never below it."""
    b = registration.bar()
    assert b.status_count >= 294 and b.count == max(c for c in (b.status_count, b.header_count) if c)


# ---------------------------------------------------------------- 2.9
def _graded(cells: dict, lines_per_game: int = 10) -> pd.DataFrame:
    """cells: (season, market) -> (n, under wins), every p = 0.5."""
    rows, gid = [], 0
    for (season, market), (n, wins) in cells.items():
        for i in range(n):
            if i % lines_per_game == 0:
                gid += 1
            rows.append({"role": L.CLOSE, "status": "", "season": season, "market": market, "event_id": f"g{gid}",
                         "win": float(i < wins), "p_power": 0.5, "p_add": 0.5, "p_mult": 0.5, "d_under": 1.91})
    return pd.DataFrame(rows)


def test_decision_act_drop_otherwise():
    rec, rush = L.PRIMARY
    strong = _graded({(s, m): (1000, 650) for s in grade.SEASONS for m in L.PRIMARY})
    d = grade.decision(strong, 0.05 / 294)
    assert d["read"] and d["condition_1"] and d["verdict"] == "Act" and len(d["checks"]) == 5
    carried = _graded({**{(s, rec): (300, 180) for s in grade.SEASONS}, **{(s, rush): (300, 120) for s in grade.SEASONS}})
    d = grade.decision(carried, 0.05 / 294)                    # pooled 0: and without receiving, below zero
    assert d["verdict"] == "Drop"
    one_market = _graded({**{(s, rec): (300, 165) for s in grade.SEASONS}, **{(s, rush): (300, 140) for s in grade.SEASONS}})
    d = grade.decision(one_market, 0.05 / 294)                 # pooled above zero, receiving carries it
    assert d["pooled"]["excess"] > 0 and d["without"][f"without {rec}"] <= 0 and d["verdict"] == "Drop"
    modest = _graded({(s, m): (100, 55) for s in grade.SEASONS for m in L.PRIMARY})
    d = grade.decision(modest, 0.05 / 294)
    assert d["verdict"] == "Otherwise" and not d["condition_1"]
    assert grade.decision(strong, None)["verdict"] == "Otherwise"        # no bar read: condition 1 can't be met
    assert grade.decision(strong[strong.season != 2023], 0.05 / 294)["read"] is False


# ---------------------------------------------------------------- 2.7: the roster
def test_name_key():
    k = roster.key
    assert k("Amon-Ra St. Brown") == k("Amon-Ra St Brown") == k("amon ra st. brown") == "amonrastbrown"
    assert k("D.J. Moore") == k("DJ Moore") and k("Kenneth Walker III") == k("Kenneth Walker")
    assert k("Marvin Harrison Jr.") == k("Marvin Harrison") and k("Ja'Marr Chase") == "jamarrchase"
    assert k("V") == "v" and k("") == ""


def test_name_map_matching():
    r = pd.DataFrame([(2025, "KC", "a", "Gabe Davis", "Gabriel", "Gabe", "Davis"),
                      (2025, "BUF", "a", "Gabe Davis", "Gabriel", "Gabe", "Davis"),      # traded: same player
                      (2025, "DET", "b", "Chris Smith", "Chris", "Chris", "Smith"),
                      (2025, "CHI", "c", "Chris Smith", "Christopher", "Chris", "Smith"),
                      (2025, "MIA", "", "No Id", "No", "No", "Id"),
                      (2024, "KC", "d", "Old Name", "Old", "Old", "Name")], columns=roster.COLUMNS)
    m = roster.NameMap(r)
    assert m.match(2025, ("KC", "BUF"), "Gabriel Davis") == ("a", "")
    assert m.match(2025, ("KC", "LV"), "Gabe Davis") == ("a", "")
    assert m.match(2025, ("DET", "CHI"), "Chris Smith") == (None, roster.SEVERAL)
    assert m.match(2025, ("DET", "GB"), "Chris Smith") == ("b", "")
    assert m.match(2025, ("NYJ", "NE"), "Gabe Davis") == (None, roster.NO_PLAYER)      # not on either team
    assert m.match(2025, ("KC", "BUF"), "Old Name") == (None, roster.NO_PLAYER)        # other season
    assert m.match(2025, ("MIA", "NE"), "No Id") == (None, roster.NO_ID)
    assert m.match(2025, ("KC", "BUF"), "Davis") == (None, roster.NO_PLAYER)          # never a last name alone


def test_roster_reader_refuses_extra_columns_and_2026(tmp_path):
    base = pd.DataFrame([(2025, "KC", "a", "A B", "A", "A", "B")], columns=roster.COLUMNS)
    base.to_csv(tmp_path / "ok.csv", index=False)
    assert len(roster.load(tmp_path / "ok.csv")) == 1
    base.assign(receiving_yards=10).to_csv(tmp_path / "extra.csv", index=False)
    with pytest.raises(SystemExit, match="expected exactly"):
        roster.load(tmp_path / "extra.csv")
    base.assign(season=2026).to_csv(tmp_path / "sealed.csv", index=False)
    with pytest.raises(SystemExit, match="refused"):
        roster.load(tmp_path / "sealed.csv")
    with pytest.raises(SystemExit, match="2026 is sealed"):
        roster._fetch(2026, tmp_path)


def test_roster_reduce_keeps_only_the_map_columns():
    weekly = pd.DataFrame({"season": [2025] * 4, "team": ["KC", "KC", "BUF", "GB"], "gsis_id": ["a", "a", "a", None],
                           "full_name": ["A B"] * 4, "first_name": ["A"] * 4, "football_name": ["A"] * 4,
                           "last_name": ["B"] * 4, "week": [1, 2, 9, 9], "status": ["ACT", "INA", "ACT", "ACT"]})
    r = roster.reduce(weekly[roster.SOURCE_COLUMNS], 2025)
    assert list(r.columns) == roster.COLUMNS and len(r) == 2 and set(r.team) == {"KC", "BUF"}    # no id: left out
    with pytest.raises(SystemExit):
        roster.reduce(weekly[roster.SOURCE_COLUMNS].assign(season=2026), 2025)


def test_the_committed_roster():
    """config/props/nfl_rosters_2023_2025.csv: the map's columns only, 2023-25 only, player ids in nflverse's form,
    and a few real spellings resolve."""
    r = roster.load()
    assert list(r.columns) == roster.COLUMNS and set(r.season) == set(roster.SEASONS)
    assert r.player_id.str.fullmatch(r"00-\d{7}").all()                 # every row has an nflverse id
    assert set(r.team) == set(pd.read_csv(Path(L.__file__).parents[4] / "config/teams/nfl.csv").code)
    m = roster.NameMap(r)
    assert m.match(2025, ("PHI", "DAL"), "A.J. Brown")[0] == m.match(2025, ("PHI", "DAL"), "AJ Brown")[0] is not None
    assert m.match(2025, ("DET", "GB"), "Amon-Ra St. Brown")[0] is not None
    assert m.match(2025, ("SEA", "LA"), "Kenneth Walker")[0] is not None


# ---------------------------------------------------------------- the snapshots and the schedule
def test_close_and_t24_are_the_puller_snapshots(fx):
    f, calls, *_ = fx
    kick = fixture.t(fixture.GAMES["f1"][0])
    f1 = sorted(c.at for c in calls if c.event_id == "f1")
    assert f1 == [kick - pd.Timedelta(hours=24), kick - pd.Timedelta(minutes=5)]       # 17:00 kickoff: close 16:55
    assert {L.role_of(c, kick) for c in calls if c.event_id == "f1"} == {L.CLOSE, L.T24}


def test_nfl_season_by_date():
    ts = lambda s: pd.Timestamp(s).to_pydatetime()       # noqa: E731
    assert L.nfl_season(ts("2025-09-05T00:20Z")) == 2025 and L.nfl_season(ts("2026-02-09T00:30Z")) == 2025
    assert L.nfl_season(ts("2026-09-10T00:20Z")) == 2026


def test_event_matching_uses_team_names_and_the_date(fx):
    f, *_ = fx
    sched = outcomes.nfl_schedule(f.games)
    ev = pd.DataFrame([{"event_id": "f1", "kick": pd.Timestamp("2025-09-07T17:00Z"), "home_team": "Kansas City Chiefs",
                        "away_team": "Baltimore Ravens"},
                       {"event_id": "x", "kick": pd.Timestamp("2025-09-20T17:00Z"), "home_team": "Kansas City Chiefs",
                        "away_team": "Baltimore Ravens"},
                       {"event_id": "y", "kick": pd.Timestamp("2025-09-07T17:00Z"), "home_team": "Nowhere Team",
                        "away_team": "Baltimore Ravens"}])
    m, why, missed = outcomes.match_events(ev, sched)
    assert m.game_id.tolist() == ["2025_01_BAL_KC"] and m.kick_nflverse.iloc[0] == pd.Timestamp("2025-09-07T17:00Z")
    assert missed == {"x": "no nflverse game", "y": "team name unknown"}


def test_no_order_code_in_the_grader():
    src = Path(L.__file__).parent
    text = "\n".join(p.read_text() for p in src.glob("*.py"))
    assert not re.search(r"\.(post|put|patch|delete)\(", text, flags=re.I)
