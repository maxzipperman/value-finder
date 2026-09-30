"""Amendment 1 to the price engine's registration (sharp-markets/docs/PRICE_ENGINE_PREREGISTRATION.md, "Amendment
1"), item by item, on made-up input only. Nothing here is data."""
import math
from collections import Counter

import numpy as np
import pandas as pd
import pytest

from markets.oddsapi import bulk
from markets.research.price_engine import engine, fixture, model, outcomes, quotes
from markets.research.price_engine import names_preflight as pf
from markets.research.price_engine import run as pe_run

NFL, CFB = model.NFL, model.CFB
T = pd.Timestamp
H1_TOT = engine.Variant("H1", NFL, "totals", "pinnacle", 0.02)


def _cell(seasons, books=("draftkings", "fanduel", "betmgm")):
    """seasons: list of (label, bets, bets with a Pinnacle close, mean CLV of those). Every bet has a final score."""
    rows, i = [], 0
    for label, n, closed, clv in seasons:
        for j in range(n):
            c = (clv + (j % 3 - 1) * 0.1) if j < closed else np.nan
            rows.append(dict(event_id=f"g{i}", season=label, book=books[i % len(books)], clv_pin_cents=c,
                             clv_own_cents=1.0, clv_pin_pts=0.0, clv_own_pts=0.0, pin_moved=False,
                             clv_pin_expected=1.0, ev_entry=0.02, gap=np.nan, hours_before=24.0, pin_stale=False,
                             won=1.0 if i % 2 else 0.0, push=0.0, profit=1.0 if i % 2 else -1.0))
            i += 1
    g = pd.DataFrame(rows)
    return g, engine.summarize(H1_TOT, g) | {"primary": True, "clv_pin_p": 1e-6}


# ---------------------------------------------------------------- the two readings the amendment replaces
def _written(g) -> bool:
    """The registered sentence read literally: seasons with 20 or more BETS; CLV above zero in all but at most one."""
    by = g.groupby("season").agg(bets=("event_id", "size"), clv=("clv_pin_cents", "mean"))
    counted = by[by.bets >= 20]
    return len(counted) >= 3 and int((counted.clv > 0).sum()) >= len(counted) - 1


def _coded(g) -> bool:
    """The code before amendment 1: seasons with 20 or more bets with a Pinnacle close."""
    by = g.groupby("season").clv_pin_cents.agg(["mean", "count"])
    counted = by[by["count"] >= 20]
    return len(counted) >= 3 and int((counted["mean"] > 0).sum()) >= len(counted) - 1


# ---------------------------------------------------------------- item 1: A2's seasons
def test_item1_a_clean_cell_passes_all_three_readings():
    """Five seasons of 30 bets, all with a Pinnacle close; four above zero, one below. The one allowed miss."""
    g, row = _cell([(str(s), 30, 30, 2.0) for s in (2020, 2021, 2022, 2023)] + [("2024", 30, 30, -1.0)])
    assert (row["seasons_counted"], row["seasons_20_closes"], row["seasons_positive"]) == (5, 5, 4)
    assert engine.a2(row) and _written(g) and _coded(g)
    assert engine.decide(row, 1.0) == "act: paper forward test"


def test_item1_the_allowed_miss_can_be_a_season_short_of_closes():
    """2023 has 25 bets but only 10 Pinnacle closes: counted, not above zero (whatever its CLV), and the one season
    A2 lets miss. Both earlier readings pass too."""
    g, row = _cell([("2020", 40, 40, 2.0), ("2021", 40, 40, 2.0), ("2022", 40, 40, 2.0), ("2023", 25, 10, 5.0)])
    assert (row["seasons_counted"], row["seasons_20_closes"], row["seasons_positive"]) == (4, 3, 3)
    assert engine.a2(row) and _written(g) and _coded(g)
    # a second such season is one miss too many
    g, row = _cell([("2020", 40, 40, 2.0), ("2021", 40, 40, 2.0), ("2022", 40, 40, 2.0), ("2023", 25, 10, 5.0),
                    ("2024", 25, 10, 5.0)])
    assert _written(g) and _coded(g) and not engine.a2(row)


def test_item1_a_cell_that_passes_the_new_a2_passes_both_earlier_readings():
    """400 made-up cells of 2 to 6 seasons, each season 0 to 45 bets with 0 to all of them closed and a mean CLV
    either side of zero. Whenever the amended A2 holds, the written sentence and the old code both hold."""
    rng = np.random.default_rng(930)
    passed = 0
    for _ in range(400):
        seasons = []
        for s in rng.choice(np.arange(2020, 2026), rng.integers(2, 7), replace=False):
            n = int(rng.integers(0, 46))            # weighted toward cells that pass, so the check has cases
            seasons.append((str(s), n, int(rng.integers(max(0, n - 25), n + 1)),
                            float(rng.choice([-1.0, 0.5, 2.0, 2.0, 2.0]))))
        seasons = [x for x in seasons if x[1] > 0] or [("2020", 1, 1, 1.0)]
        g, row = _cell(seasons)
        if engine.a2(row):
            passed += 1
            assert _written(g) and _coded(g), seasons
    assert passed >= 20                                           # the check is not empty


def test_item1_results_csv_prints_both_counts(tmp_path):
    from argparse import Namespace
    import tempfile

    from markets.research.price_engine import run as pe_run
    old = tempfile.tempdir
    tempfile.tempdir = str(tmp_path)
    try:
        assert pe_run.main(Namespace(fixture=True, out=str(tmp_path / "out"))) == 0
    finally:
        tempfile.tempdir = old
    res = pd.read_csv(tmp_path / "out" / "results.csv")
    assert {"seasons_counted", "seasons_20_closes", "seasons_positive", "graded"} <= set(res.columns)
    report = (tmp_path / "out" / "report.md").read_text()
    header = next(line for line in report.splitlines() if line.startswith("| variant |"))
    assert "| graded |" in header and "| seasons_20_closes |" in header


# ---------------------------------------------------------------- item 3: K3's tie
def test_item3_one_top_book_is_unchanged():
    g, row = _cell([("2020", 40, 40, 1.0), ("2021", 40, 40, 1.0), ("2022", 40, 40, 1.0)])
    g["book"] = ["draftkings"] * 70 + ["fanduel"] * 50
    g["clv_pin_cents"] = [3.0] * 70 + [-1.0] * 50
    r = engine.summarize(H1_TOT, g)
    assert r["top_book"] == "draftkings" and r["clv_pin_wo_top_book"] == pytest.approx(-1.0)


def test_item3_three_tied_books_and_a_removal_that_leaves_no_closes():
    g, _ = _cell([("2020", 40, 40, 1.0), ("2021", 40, 40, 1.0), ("2022", 40, 40, 1.0)])
    g["book"] = ["betmgm"] * 40 + ["draftkings"] * 40 + ["fanduel"] * 40
    g["clv_pin_cents"] = [2.0] * 40 + [1.0] * 40 + [4.0] * 40
    for order in (g, g.iloc[::-1], g.sample(frac=1, random_state=3)):
        r = engine.summarize(H1_TOT, order)
        assert r["top_book"] == "betmgm+draftkings+fanduel"
        assert r["clv_pin_wo_top_book"] == pytest.approx(1.5)     # the lowest of 2.5, 3.0 and 1.5
    # two books tie, and every Pinnacle close is at one of them: removing it leaves no CLV, and K3 kills
    g2 = g[g.book != "betmgm"].copy()
    g2.loc[g2.book == "fanduel", "clv_pin_cents"] = np.nan
    r = engine.summarize(H1_TOT, g2)
    assert r["top_book"] == "draftkings+fanduel" and math.isnan(r["clv_pin_wo_top_book"])
    row = r | {"primary": True, "clv_pin_p": 1e-6, "clv_pin_n": 500, "bets": 500}
    assert "one book carries it" in engine.decide(row, 1.0)


# ---------------------------------------------------------------- item 4: K2 needs results
def test_item4_too_few_results_cannot_act_but_can_still_be_killed():
    g, row = _cell([(str(s), 40, 40, 2.0) for s in (2020, 2021, 2022)])
    assert row["graded"] == 120 and engine.decide(row, 1.0) == "act: paper forward test"
    unscored = g.assign(won=np.nan, push=np.nan, profit=np.nan)
    unscored.loc[:98, ["won", "push"]] = [1.0, 0.0]
    unscored.loc[:98, "profit"] = 0.9
    r = engine.summarize(H1_TOT, unscored) | {"primary": True, "clv_pin_p": 1e-6}
    assert r["graded"] == 99 and engine.decide(r, 1.0) == engine.TOO_FEW_RESULTS
    # a push has a final score but no return: 100 scored bets with one push are still too few results
    pushed = unscored.copy()
    pushed.loc[99, ["won", "push", "profit"]] = [0.0, 1.0, np.nan]
    r = engine.summarize(H1_TOT, pushed) | {"primary": True, "clv_pin_p": 1e-6}
    assert r["graded"] == 99 and engine.decide(r, 1.0) == engine.TOO_FEW_RESULTS
    # K1 still kills a cell with no results at all
    r = engine.summarize(H1_TOT, unscored.assign(clv_pin_cents=-1.0)) | {"primary": True}
    assert engine.decide(r, 1.0).startswith("kill: CLV at or below zero")


# ---------------------------------------------------------------- item 8: team names
def test_item8_every_alias_names_a_school_spelled_as_the_score_table_spells_it():
    """The alias table's schools, against the committed college score table (2020-25, read with the season filter)."""
    g = outcomes.cfb_games()
    schools = set(g.home_team) | set(g.away_team)
    assert set(outcomes.CFB_ALIASES.values()) <= schools
    assert all(k == outcomes.norm(k) for k in outcomes.CFB_ALIASES)          # keys are normalized names
    assert len(outcomes.CFB_ALIASES) == 40


def test_item8_the_alias_table_comes_before_the_team_files_and_the_prefix_rule():
    o = outcomes
    schools = ["Miami", "Miami (OH)", "North Carolina", "NC State", "Southern", "USC", "Georgia"]
    by_len = sorted(((o.norm(s), s) for s in schools), key=lambda x: -len(x[0]))
    wrong_files = {"miami redhawks": "Miami"}                                # even a wrong team-file entry loses
    assert o.resolve_cfb("Miami RedHawks", wrong_files, by_len) == ("Miami (OH)", o.ALIAS)
    assert o.resolve_cfb("North Carolina State Wolfpack", {}, by_len) == ("NC State", o.ALIAS)
    assert o.resolve_cfb("Southern California Trojans", {}, by_len) == ("USC", o.ALIAS)
    assert o.resolve_cfb("Georgia Bulldogs", {"georgia bulldogs": "Georgia"}, by_len) == ("Georgia", o.TEAM_FILES)
    assert o.resolve_cfb("Georgia Bulldogs", {}, by_len) == ("Georgia", o.PREFIX)
    assert o.resolve_cfb("Georgia", {}, by_len) == ("Georgia", o.SCHOOL_NAME)
    assert o.resolve_cfb("Nowhere Nobodies", {}, by_len) == (None, o.UNRESOLVED)


def test_item8_prefix_and_unresolved_names_are_logged_under_their_own_reasons(tmp_path):
    cfb = pd.DataFrame(dict(season=[2024] * 2, start_utc=[T("2024-09-07T16:00Z"), T("2024-09-14T16:00Z")],
                            home_team=["Georgia", "Texas"], away_team=["Alabama", "Oklahoma"],
                            home_score=[1.0, 2.0], away_score=[0.0, 0.0]))
    ev = pd.DataFrame(dict(sport=CFB, event_id=["ok", "moved", "unknown", "alias_no_game"],
                           kickoff=[T("2024-09-07T16:00Z"), T("2024-09-10T16:00Z"), T("2024-09-14T16:00Z"),
                                    T("2024-09-14T16:00Z")],
                           home=["Georgia Bulldogs", "Georgia Bulldogs", "Nowhere Nobodies", "Mississippi Rebels"],
                           away=["Alabama Crimson Tide", "Alabama Crimson Tide", "Oklahoma Sooners", "Texas"]))
    detail: dict = {}
    got, why = outcomes.match(ev, cfb=cfb, cfb_raw=tmp_path, detail=detail)
    assert list(got.event_id) == ["ok"]
    assert why == Counter({"cfb_prefix_name_no_game": 1, "cfb_team_name_unknown": 1, "cfb_no_game": 1})
    names = detail["names"].set_index("name")
    assert names.loc["Georgia Bulldogs", "how"] == outcomes.PREFIX and names.loc["Georgia Bulldogs", "games"] == 2
    assert names.loc["Mississippi Rebels", "resolves_to"] == "Ole Miss"
    assert names.loc["Nowhere Nobodies", "how"] == outcomes.UNRESOLVED and detail["cfb_team_files"] == 0
    assert set(detail["unmatched"].reason) == {"cfb_prefix_name_no_game", "cfb_team_name_unknown", "cfb_no_game"}


def _empty_results():
    return pd.DataFrame(columns=pe_run.RESULT_COLS + ["market", "primary"])


def test_item8_the_report_prints_the_share_matched_and_whether_the_team_files_were_found():
    q = pd.DataFrame(dict(sport=[NFL] * 3 + [CFB] * 20, season=["2024"] * 3 + ["2021"] * 20,
                          event_id=[f"n{i}" for i in range(3)] + [f"c{i}" for i in range(20)]))
    scores = pd.DataFrame(dict(sport=[NFL] * 3 + [CFB] * 18, event_id=[f"n{i}" for i in range(3)]
                               + [f"c{i}" for i in range(18)], home_score=1.0, away_score=0.0))
    cov = pe_run.score_coverage(q, scores).set_index("sport")
    assert (cov.loc["CFB", "matched"], cov.loc["CFB", "games"]) == (18, 20) and cov.loc["NFL", "share"] == 1.0
    names = pd.DataFrame(dict(sport=[CFB, CFB], name=["Georgia Bulldogs", "Nowhere Nobodies"],
                              resolves_to=["Georgia", None], how=["prefix rule", "unresolved"], games=[3, 1]))
    res = {"coverage": pe_run.score_coverage(q, scores), "names": names, "cfb_team_files": 0}
    first_page = pe_run.report(res, _empty_results(), fixture=False).split("## Results")[0]
    assert "fewer than 95% of games were matched to a final score in CFB 2021 (90.0%, 18 of 20)" in first_page
    assert "were NOT found" in first_page and "2 distinct names resolved only by the prefix rule" in first_page
    res["cfb_team_files"] = 4
    res["coverage"] = pe_run.score_coverage(q, pd.concat([scores, scores.iloc[-2:].assign(event_id=["c18", "c19"])]))
    first_page = pe_run.report(res, _empty_results(), fixture=False).split("## Results")[0]
    assert "fewer than 95%" not in first_page and "were found (4 files)" in first_page


def _schedule(tmp_path, cfg, sport, games):
    bulk.save_schedule(tmp_path / "raw", sport, [
        bulk._label(cfg, {"id": i, "sport": sport, "commence_time": T(k).to_pydatetime(), "home_team": h,
                          "away_team": a, "first_seen": None}) for i, k, h, a in games])


def test_item8_the_names_preflight_on_a_made_up_schedule(tmp_path, monkeypatch, capsys):
    """Names and kickoffs only. A sealed 2026 game and a game outside every season window are dropped as they are
    read; the made-up score tables' scores never appear in any output (the preflight plants row numbers)."""
    cfg = fixture.config(tmp_path)                    # windows: 2024 (unsealed) and 2026 (sealed)
    _schedule(tmp_path, cfg, NFL, [("n1", "2024-09-08T17:00Z", "Kansas City Chiefs", "Baltimore Ravens"),
                                   ("n2", "2024-09-15T17:00Z", "Nowhere Nobodies", "Baltimore Ravens"),
                                   ("n26", "2026-09-13T17:00Z", "Buffalo Bills", "New York Jets")])
    _schedule(tmp_path, cfg, CFB, [("c1", "2024-09-07T16:00Z", "Miami RedHawks", "Cincinnati Bearcats"),
                                   ("c2", "2024-09-07T19:30Z", "Georgia Bulldogs", "Alabama Crimson Tide"),
                                   ("c2-relisted", "2024-09-07T19:30Z", "Georgia Bulldogs", "Alabama Crimson Tide"),
                                   ("c3", "2024-09-14T19:30Z", "Nowhere Nobodies", "Texas Longhorns"),
                                   ("c4", "2024-09-21T19:30Z", "Georgia Bulldogs", "Texas Longhorns"),
                                   ("c26", "2026-09-12T19:30Z", "Ohio State Buckeyes", "Oregon Ducks"),
                                   ("c-summer", "2024-07-01T19:30Z", "Georgia Bulldogs", "Texas Longhorns")])
    nfl = pd.DataFrame(dict(season=[2024], day=[T("2024-09-08").date()], home_team=["KC"], away_team=["BAL"],
                            home_score=[77.0], away_score=[66.0]))
    cfb = pd.DataFrame(dict(season=[2024] * 3,
                            start_utc=[T("2024-09-07T16:00Z"), T("2024-09-07T19:30Z"), T("2024-10-05T19:30Z")],
                            home_team=["Miami (OH)", "Georgia", "Texas"],
                            away_team=["Cincinnati", "Alabama", "Alabama"],
                            home_score=[77.0, 55.0, 88.0], away_score=[66.0, 44.0, 99.0]))
    monkeypatch.setattr(pf.bulk, "load_config", lambda: cfg)
    monkeypatch.setattr(pf, "nfl_schedule", lambda: nfl)
    monkeypatch.setattr(pf, "cfb_schedule", lambda: cfb)
    monkeypatch.setattr(pf, "fbs_schools", lambda: {"Miami (OH)", "Georgia", "Alabama", "Cincinnati", "Texas",
                                                    "Ohio State"})
    out = tmp_path / "out"
    assert pf.main(["--out", str(out), "--raw-dir", str(tmp_path / "raw"), "--cfb-raw", str(tmp_path / "none")]) == 0
    printed = capsys.readouterr().out
    assert "MISSING" in printed and "sealed or outside the season windows': 2" in printed
    names = pd.read_csv(out / "names.csv")
    assert list(names.how[:2]) == ["prefix rule", "prefix rule"]              # prefix rows first
    assert {"Miami RedHawks", "Georgia Bulldogs", "Nowhere Nobodies"} <= set(names.name)
    assert not {"Ohio State Buckeyes", "Buffalo Bills"} & set(names.name)       # the sealed games were never read
    by = names.set_index("name")
    assert by.loc["Miami RedHawks", "how"] == outcomes.ALIAS and by.loc["Miami RedHawks", "resolves_to"] == "Miami (OH)"
    un = pd.read_csv(out / "unmatched.csv").set_index("event_id").reason.to_dict()
    assert un == {"n2": "nfl_team_name_unknown", "c3": "cfb_team_name_unknown", "c4": "cfb_prefix_name_no_game"}
    assert set(pd.read_csv(out / "one_game_two_events.csv").event_id) == {"c2", "c2-relisted"}
    assert "1 of 3 matched games (33.33%): MORE THAN 1 IN 100" in printed
    assert set(pd.read_csv(out / "unreached.csv").school) == {"Ohio State"}
    for f in out.glob("*.csv"):                                               # no real score anywhere
        assert not any(x in f.read_text() for x in ("77", "66", "55", "44", "88", "99")), f.name
    # no saved schedule: nothing to check
    assert pf.main(["--out", str(tmp_path / "out2"), "--raw-dir", str(tmp_path / "empty")]) == 0
    assert "nothing to check" in capsys.readouterr().out


# ---------------------------------------------------------------- item 7: the numbers the registration did not state
# The season windows that label each game's season (by the UTC date of its latest-listed kickoff, both ends
# included), as amendment 1 writes them out. Changing one in config/odds5m.yaml is an amendment: this test fails.
SEASON_WINDOWS = {
    NFL: [("2020", "2020-09-01", "2021-02-15", False), ("2021", "2021-09-01", "2022-02-20", False),
          ("2022", "2022-09-01", "2023-02-20", False), ("2023", "2023-09-01", "2024-02-15", False),
          ("2024", "2024-09-01", "2025-02-15", False), ("2025", "2025-09-01", "2026-02-15", False),
          ("2026", "2026-09-01", "2027-02-20", True)],
    CFB: [("2020", "2020-08-25", "2021-01-15", False), ("2021", "2021-08-20", "2022-01-15", False),
          ("2022", "2022-08-20", "2023-01-15", False), ("2023", "2023-08-20", "2024-01-15", False),
          ("2024", "2024-08-20", "2025-01-25", False), ("2025", "2025-08-20", "2026-01-25", False),
          ("2026", "2026-08-20", "2027-01-25", True)],
}


def test_item7_the_season_windows_are_the_ones_amendment_1_writes_out():
    cfg = bulk.load_config()
    for sport, want in SEASON_WINDOWS.items():
        got = [(w["label"], w["from"].isoformat(), w["to"].isoformat(), w["sealed"])
               for w in cfg["sports"][sport]["windows"]]
        assert got == want, sport
    # both ends are inside the window, by the kickoff's UTC date
    from datetime import datetime, timezone
    at = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc)      # noqa: E731
    assert bulk.window_for(cfg, NFL, at("2021-02-15T23:59:00"))["label"] == "2020"
    assert bulk.window_for(cfg, NFL, at("2021-02-16T00:00:00")) is None
    assert bulk.window_for(cfg, CFB, at("2021-08-20T00:00:00"))["label"] == "2021"


def test_item7_the_constants_amendment_1_states():
    from datetime import timedelta
    import inspect

    assert (engine.MIN_BETS, engine.MIN_SEASON_BETS, engine.EPS) == (100, 20, 1e-9)
    assert engine.LAG_POINTS == 1.0 and engine.LAG_MIN_DEC == 1 + 100 / 115
    assert engine.CLOSE_WINDOW == pd.Timedelta(minutes=60) and engine.EV_ERROR == 0.10
    assert quotes.WINDOW == timedelta(days=7) and quotes.COARSE_MARGIN == timedelta(days=2)
    assert outcomes.CFB_WINDOW == pd.Timedelta(hours=36)
    assert outcomes.EXTRA_NFL == {"washington football team": "WAS", "washington redskins": "WAS",
                                  "oakland raiders": "LV"}
    assert "batch" not in inspect.signature(quotes.load_quotes).parameters     # no batch size remains (item 2)


def test_item7_minus_115_is_a_decimal_price_of_1_plus_100_over_115_or_more():
    """1 + 100/115 = 1.869565...: 1.8696 is -115 or better; 1.8695 is not. (The registration's "decimal 1.87" is
    rounded.) The 1-point gap is inclusive too."""
    snap, k = T("2024-09-07T16:00Z"), T("2024-09-08T17:00Z")
    base = dict(sport=NFL, season="2024", event_id="e", kickoff=k, commence=k, home="H", away="A", snap=snap,
                market="totals", upd=pd.NaT)
    for dec, want in ((1.8696, 1), (1.8695, 0)):
        q = pd.DataFrame([dict(base, book="pinnacle", line=44.5, dec_a=1.95, dec_b=1.95),
                          dict(base, book="fanduel", line=45.5, dec_a=1.95, dec_b=dec)])
        e = engine.entries(engine.side_rows(q, engine.fair_table(q)), engine.Variant("H2", NFL, "totals", "lag", 1.0))
        assert len(e) == want, dec


def test_item7_h2_takes_the_biggest_gap_then_the_best_price_then_the_book_name():
    snap, k = T("2024-09-07T16:00Z"), T("2024-09-08T17:00Z")
    base = dict(sport=NFL, season="2024", event_id="e", kickoff=k, commence=k, home="H", away="A", snap=snap,
                market="totals", upd=pd.NaT)

    def pick(books):
        q = pd.DataFrame([dict(base, book="pinnacle", line=44.5, dec_a=1.95, dec_b=1.95)]
                         + [dict(base, book=b, line=ln, dec_a=1.80, dec_b=d) for b, ln, d in books])
        e = engine.entries(engine.side_rows(q, engine.fair_table(q)), engine.Variant("H2", NFL, "totals", "lag", 1.0))
        return e.book.iloc[0]
    assert pick([("draftkings", 45.5, 2.10), ("fanduel", 46.0, 1.87)]) == "fanduel"        # the gap first
    assert pick([("draftkings", 45.5, 1.90), ("fanduel", 45.5, 1.95)]) == "fanduel"        # then the price
    assert pick([("fanduel", 45.5, 1.95), ("draftkings", 45.5, 1.95)]) == "draftkings"     # then the book's name
    # the one score, gap x 1000 + price, keeps "gap, then price" only while the smaller gap's price is less than
    # 500 above the other's (gaps differ by 0.5 or more): at 1002 (the auditor's D8 case) the smaller gap goes first
    assert pick([("draftkings", 45.5, 500.0), ("fanduel", 46.0, 1.95)]) == "fanduel"
    assert pick([("draftkings", 45.5, 1002.0), ("fanduel", 46.0, 1.95)]) == "draftkings"


def test_item7_a4_cuts_at_an_ev_of_010_strictly_with_no_tolerance():
    """A4's mean is over bets with ev_entry < 0.10, strict and with no 1e-9 tolerance; bets_ev_10plus counts the
    rest (ev_entry >= 0.10)."""
    g, _ = _cell([("2020", 30, 30, 1.0)])
    g["clv_pin_cents"] = [5.0] * 10 + [1.0] * 20
    g["ev_entry"] = [0.10] * 10 + [0.10 - 1e-10] * 20        # 0.10 - 1e-10 is "0.10" to the flags' tolerance
    row = engine.summarize(H1_TOT, g)
    assert row["bets_ev_10plus"] == 10 and row["clv_pin_ev_below_10"] == pytest.approx(1.0)


def test_item7_the_statistics_as_coded():
    from statistics import NormalDist
    x, games = [2.0, 1.0, -1.0, 3.0, 0.5, 1.5], ["a", "a", "b", "c", "c", "d"]
    mean, se, n, p = engine.cmean(x, games)
    dev = pd.Series(np.array(x) - mean).groupby(games).sum().to_numpy()
    k = len(dev)
    assert se == pytest.approx(math.sqrt((dev ** 2).sum() * k / (k - 1)) / n)       # game-clustered, k/(k-1)
    assert p == pytest.approx(1 - NormalDist().cdf(mean / se))                      # one-sided, the normal curve
    assert math.isnan(engine.cmean([1.0, 2.0], ["a", "a"])[1])                      # one game: no SE, no p
    # the return interval: mean +/- 1.96 game-clustered SEs, and only with 2 or more graded bets
    g, row = _cell([("2020", 30, 30, 1.0)])
    rmean, rse, _, _ = engine.cmean(g.profit, g.event_id)
    assert (row["roi_lo"], row["roi_hi"]) == (pytest.approx(rmean - 1.96 * rse), pytest.approx(rmean + 1.96 * rse))
    one = engine.summarize(H1_TOT, g.iloc[:1])
    assert one["graded"] == 1 and math.isnan(one["roi_lo"]) and math.isnan(one["roi_hi"])


# ---------------------------------------------------------------- item 2: every quote counted once
def _quote(eid, snap, commence, book, market="totals", under=1.95):
    """bulk.load_rows-style outcome rows for one book's market at one snapshot (made up)."""
    names = ("Over", "Under") if market == "totals" else ("H", "A")
    return [{"sport": NFL, "pull": "F1", "snapshot_ts": snap, "requested_ts": snap, "odds_event_id": eid,
             "commence_time": commence, "home_team": "H", "away_team": "A", "bookmaker": book,
             "book_last_update": snap, "market_key": market, "market_last_update": snap, "outcome_name": n,
             "description": None, "point": "44.5", "price_decimal": str(pr), "origin": "historical"}
            for n, pr in zip(names, (1.95, under))]


def _snapshot(snap, dk_under=2.10):
    """One made-up snapshot: g1 (kept), g2 (listed after its kickoff), g3 (more than 9 days out), two books each,
    plus one row of a market that isn't featured: 7 quotes."""
    rows = []
    for eid, ko in (("g1", "2024-09-08T17:00:00Z"), ("g2", "2024-09-07T15:00:00Z"), ("g3", "2024-09-20T17:00:00Z")):
        rows += _quote(eid, snap, ko, "pinnacle") + _quote(eid, snap, ko, "draftkings", under=dk_under)
    return rows + _quote("g1", snap, "2024-09-08T17:00:00Z", "pinnacle", market="alternate_totals")[:1]


def test_item2_every_quote_of_a_repeated_snapshot_is_counted_once_as_duplicate_snapshot(monkeypatch, tmp_path):
    """Four calls: S1, S1 again, S2, S2 again with a different DraftKings price. Every quote of a repeated snapshot
    is counted once, as duplicate_snapshot, before any other reason: the second copies of g2 and g3 are not counted
    again as at_or_after_kickoff or more_than_7_days_before_kickoff. Quotes read = kept + every drop reason;
    duplicate_snapshot_conflicting_price is a sub-count of duplicate_snapshot."""
    s1, s2 = "2024-09-07T16:00:00Z", "2024-09-08T16:30:00Z"
    close = _quote("g1", s2, "2024-09-08T17:00:00Z", "pinnacle") + _quote("g1", s2, "2024-09-08T17:00:00Z",
                                                                         "draftkings")
    close_moved = _quote("g1", s2, "2024-09-08T17:00:00Z", "pinnacle") + _quote("g1", s2, "2024-09-08T17:00:00Z",
                                                                               "draftkings", under=1.99)
    batches = [_snapshot(s1), _snapshot(s1), close, close_moved]
    read = 7 + 7 + 2 + 2
    for order in (batches, batches[::-1], [batches[0], batches[2], batches[1], batches[3]]):
        monkeypatch.setattr(quotes.bulk, "load_rows", lambda cfg, calls, cache, b=order: sum((b[i] for i in calls), []))
        q, drops = quotes.load_quotes(fixture.config(tmp_path), list(range(len(order))), None)
        assert len(q) == 4 and set(q.event_id) == {"g1"}
        assert drops["duplicate_snapshot"] == 9
        assert (drops["at_or_after_kickoff"], drops["more_than_7_days_before_kickoff"]) == (2, 2)
        assert drops["market_not_featured"] == 1 and drops["duplicate_snapshot_conflicting_price"] == 1
        dropped = sum(v for k, v in drops.items() if k != "duplicate_snapshot_conflicting_price")
        assert len(q) + dropped == read


# ---------------------------------------------------------------- item 5: the spread cohort's reader
def test_item5_the_spread_cohort_reader_filters_the_seasons_as_it_reads(tmp_path, monkeypatch):
    """model.spread_pairs_from_tables reads only the cohort's seasons (NFL 1999-2019, CFB 2006-2019): a 2026 row
    and a 2020 row in the file never reach it."""
    (tmp_path / "nfl-weather/data/processed").mkdir(parents=True)
    (tmp_path / "cfb-weather/data/processed").mkdir(parents=True)
    pd.DataFrame(dict(season=[2019, 2020, 2026], spread_line=[3.0, 3.0, 3.0], result=[7.0, 7.0, 7.0])).to_parquet(
        tmp_path / "nfl-weather/data/processed/games.parquet")
    pd.DataFrame(dict(season=np.array([2019, 2020, 2026], dtype="int32"), home_spread=[-3.0] * 3,
                      result=[7.0] * 3)).to_parquet(tmp_path / "cfb-weather/data/processed/games.parquet")
    monkeypatch.setattr(model, "REPO", tmp_path)
    seen, real = [], pd.read_parquet
    monkeypatch.setattr(pd, "read_parquet", lambda *a, **k: seen.append(real(*a, **k).season.tolist()) or real(*a, **k))
    assert [len(model.spread_pairs_from_tables(sp)[0]) for sp in (NFL, CFB)] == [1, 1]
    assert seen == [[2019], [2019]]


def test_item5_the_frozen_spread_cohort_is_unchanged_by_the_read_time_filter():
    """The processed tables in git, read with the filter, still give the registered spread cohort, both sports."""
    for sp in (NFL, CFB):
        s, m = model.spread_pairs_from_tables(sp)
        assert model.spread_cohort_hash(s, m) == model.SPREAD_COHORT_SHA256[sp], sp


# ---------------------------------------------------------------- the known limit: home and away swapped
def test_known_limit_games_listed_with_home_and_away_swapped_are_counted_not_excluded():
    rows = [dict(sport=NFL, event_id="g", home="X", away="Y"), dict(sport=NFL, event_id="g", home="Y", away="X"),
            dict(sport=NFL, event_id="h", home="X", away="Y"), dict(sport=NFL, event_id="h", home="X", away="Y"),
            dict(sport=CFB, event_id="g", home="X", away="Y")]
    assert pe_run.home_away_changed(pd.DataFrame(rows)) == 1


def test_item4_the_main_table_shows_pushes_beside_graded():
    i = pe_run.RESULT_COLS.index("graded")
    assert pe_run.RESULT_COLS[i + 1] == "pushes"
    body = pe_run.report({}, _empty_results(), fixture=False)
    assert "| graded | pushes |" in body or "_(none)_" in body


# ---------------------------------------------------------------- item 8: the preflight compares the alias table
def test_item8_the_preflight_prints_what_the_team_files_give_for_each_alias(tmp_path, monkeypatch, capsys):
    """Made-up cfbfastR team files: one name agrees with the alias table, one disagrees, the rest are not in them."""
    files = tmp_path / "cfbfastr"
    files.mkdir()
    pd.DataFrame(dict(school=["Miami (OH)", "Ole Miss"], mascot=["RedHawks", "Rebels"],
                      alt_name1=["Miami", "Nevada Las Vegas"])).to_parquet(files / "team_info_2024.parquet")
    schools = ["Miami (OH)", "Ole Miss", "UNLV", "Cincinnati"]
    al = pf.alias_check(schools, files).set_index("alias")
    assert len(al) == len(outcomes.CFB_ALIASES)
    assert al.loc["miami redhawks"].tolist() == ["Miami (OH)", "Miami (OH)", True]
    assert al.loc["nevada las vegas rebels"].tolist() == ["UNLV", "Ole Miss", False]
    assert al.loc["umass minutemen", "team_files_school"] is None and al.loc["umass minutemen", "agrees"] is None
    assert pf.alias_check(schools, tmp_path / "none").agrees.isna().all()          # no team files: nothing compared
    # through main(): printed row by row when the files are present, and written to aliases.csv
    cfg = fixture.config(tmp_path)
    _schedule(tmp_path, cfg, CFB, [("c1", "2024-09-07T16:00Z", "Miami RedHawks", "Cincinnati Bearcats")])
    cfb = pd.DataFrame(dict(season=[2024], start_utc=[T("2024-09-07T16:00Z")], home_team=["Miami (OH)"],
                            away_team=["Cincinnati"], home_score=[7.0], away_score=[3.0]))
    nfl = pd.DataFrame(columns=["season", "day", "home_team", "away_team", "home_score", "away_score"])
    monkeypatch.setattr(pf.bulk, "load_config", lambda: cfg)
    monkeypatch.setattr(pf, "nfl_schedule", lambda: nfl)
    monkeypatch.setattr(pf, "cfb_schedule", lambda: cfb.assign(home_team=["Miami (OH)"]))
    monkeypatch.setattr(pf, "fbs_schools", lambda: {"Miami (OH)"})
    monkeypatch.setattr(pf, "alias_check", lambda sch, raw, f=pf.alias_check: f(schools, raw))
    out = tmp_path / "out"
    assert pf.main(["--out", str(out), "--raw-dir", str(tmp_path / "raw"), "--cfb-raw", str(files)]) == 0
    printed = capsys.readouterr().out
    assert "alias table against the team files (1 disagree" in printed
    assert "'nevada las vegas rebels': alias table 'UNLV', team files 'Ole Miss' (DISAGREES)" in printed
    assert "'miami redhawks': alias table 'Miami (OH)', team files 'Miami (OH)' (agrees)" in printed
    assert len(pd.read_csv(out / "aliases.csv")) == len(outcomes.CFB_ALIASES)
    assert pf.main(["--out", str(out), "--raw-dir", str(tmp_path / "raw"), "--cfb-raw", str(tmp_path / "x")]) == 0
    assert f"alias table: {len(outcomes.CFB_ALIASES)} rows, not compared" in capsys.readouterr().out


# ---------------------------------------------------------------- item 8: the preflight is blind to results
# Astra's audit 3, finding 3: the preflight read the score tables through the engine's score readers, which ask for
# the score columns and drop games without a final score, so which events it matched depended on whether a score
# existed. It now reads the tables through its own schedule readers: no score column, no score-presence filter,
# the same read-time season filter. Everything below is made up.
RESULT_COLS = {"home_score", "away_score", "home_points", "away_points", "result", "total", "overtime", "completed",
               "home_post_win_prob", "away_post_win_prob", "home_postgame_elo", "away_postgame_elo",
               "excitement_index"}


def _game_tables(repo, scores: str) -> None:
    """Made-up NFL and college score tables at the repo's paths, with a sealed 2026 row in each. `scores`: "present"
    (every game has a final score), "missing" (every score and result column empty) or "absent" (no such column)."""
    nfl = pd.DataFrame(dict(season=[2024, 2024, 2024, 2026], game_type="REG",
                            gameday=["2024-09-08", "2024-09-15", "2024-09-22", "2026-09-13"],
                            home_team=["KC", "BAL", "KC", "BUF"], away_team=["BAL", "KC", "CIN", "NYJ"],
                            home_score=[77.0, 66.0, 83.0, 99.0], away_score=[55.0, 44.0, 93.0, 98.0],
                            result=[7.0, -7.0, 20.0, 1.0], total=[47.0, 41.0, 40.0, 197.0], overtime=[0.0] * 4))
    cfb = pd.DataFrame(dict(season=[2024, 2024, 2024, 2026], week=[2, 2, 6, 3],
                            start_utc=pd.to_datetime(["2024-09-07T16:00Z", "2024-09-07T19:30Z", "2024-10-05T19:30Z",
                                                      "2026-09-12T19:30Z"]),
                            home_team=["Miami (OH)", "Georgia", "Texas", "Ohio State"],
                            away_team=["Cincinnati", "Alabama", "Alabama", "Oregon"],
                            home_division="fbs", away_division="fbs", completed=True,
                            home_points=[71.0, 62.0, 87.0, 99.0], away_points=[58.0, 67.0, 96.0, 98.0],
                            excitement_index=[5.0, 6.0, 7.0, 8.0]))
    if scores == "missing":
        nfl[["home_score", "away_score", "result", "total", "overtime"]] = np.nan
        cfb[["home_points", "away_points", "excitement_index"]] = np.nan
        cfb["completed"] = False
    elif scores == "absent":
        nfl = nfl.drop(columns=["home_score", "away_score", "result", "total", "overtime"])
        cfb = cfb.drop(columns=["home_points", "away_points", "excitement_index", "completed"])
    for folder, t in (("nfl-weather", nfl), ("cfb-weather", cfb)):
        (repo / folder / "data/processed").mkdir(parents=True, exist_ok=True)
        t.to_parquet(repo / folder / "data/processed/games.parquet", index=False)


def _preflight_on_made_up_tables(tmp_path, monkeypatch, scores: str) -> tuple[dict, str]:
    """Runs main() on one made-up schedule against the made-up tables; returns {file: bytes} and what it printed."""
    run = tmp_path / scores
    repo = run / "repo"
    _game_tables(repo, scores)
    cfg = fixture.config(run)
    _schedule(run, cfg, NFL, [("n1", "2024-09-08T17:00Z", "Kansas City Chiefs", "Baltimore Ravens"),
                              ("n2", "2024-09-15T17:00Z", "Baltimore Ravens", "Kansas City Chiefs"),
                              ("n3", "2024-09-22T17:00Z", "Kansas City Chiefs", "Nowhere Nobodies"),
                              ("n26", "2026-09-13T17:00Z", "Buffalo Bills", "New York Jets")])
    _schedule(run, cfg, CFB, [("c1", "2024-09-07T16:00Z", "Miami RedHawks", "Cincinnati Bearcats"),
                              ("c2", "2024-09-07T19:30Z", "Georgia Bulldogs", "Alabama Crimson Tide"),
                              ("c2-relisted", "2024-09-07T19:30Z", "Georgia Bulldogs", "Alabama Crimson Tide"),
                              ("c3", "2024-09-14T19:30Z", "Nowhere Nobodies", "Texas Longhorns"),
                              ("c4", "2024-09-21T19:30Z", "Georgia Bulldogs", "Texas Longhorns"),
                              ("c5", "2024-10-05T19:30Z", "Texas Longhorns", "Alabama Crimson Tide"),
                              ("c26", "2026-09-12T19:30Z", "Ohio State Buckeyes", "Oregon Ducks")])
    monkeypatch.setattr(pf.bulk, "load_config", lambda path=None, f=_LOAD_CONFIG: cfg if path is None else f(path))
    monkeypatch.setattr(pf, "REPO", repo)
    monkeypatch.setattr(outcomes, "REPO", repo)        # so a return to the engine's score readers would read them too
    out = run / "out"
    assert pf.main(["--out", str(out), "--raw-dir", str(run / "raw"), "--cfb-raw", str(run / "no-team-files")]) == 0
    files = {f.name: f.read_bytes() for f in sorted(out.iterdir())}
    return files, _printed().replace(str(run), "<run>")                  # the folder is the only difference


_capture = {}
_LOAD_CONFIG = bulk.load_config


def _printed() -> str:
    return _capture["capsys"].readouterr().out


def test_item8_the_preflight_output_is_the_same_with_scores_present_missing_or_absent(tmp_path, monkeypatch, capsys):
    _capture["capsys"] = capsys
    present = _preflight_on_made_up_tables(tmp_path, monkeypatch, "present")
    assert set(present[0]) == {"names.csv", "unmatched.csv", "unreached.csv", "one_game_two_events.csv",
                               "aliases.csv"}
    # every output file byte for byte, and what it printed
    assert _preflight_on_made_up_tables(tmp_path, monkeypatch, "missing") == present
    assert _preflight_on_made_up_tables(tmp_path, monkeypatch, "absent") == present
    # and the run is not trivially empty: 6 of the 9 events in 2020-25 land on a game, with or without a score
    assert "matched events: 6 of 9 " in present[1]
    un = pd.read_csv(pd.io.common.BytesIO(present[0]["unmatched.csv"])).set_index("event_id").reason.to_dict()
    assert un == {"n3": "nfl_team_name_unknown", "c3": "cfb_team_name_unknown", "c4": "cfb_prefix_name_no_game"}
    for body in present[0].values():                        # no made-up score anywhere
        assert not any(x in body.decode() for x in ("77", "66", "83", "55", "44", "93", "71", "62", "87", "58", "67", "96", "99", "98"))


def test_item8_the_preflight_never_asks_for_a_score_column(tmp_path, monkeypatch, capsys):
    """A read spy on both parquet readers: every read names its columns, none is a score or result column, every
    read of a score table passes the season filter, and what it hands over holds no 2026 row. The engine's own
    score readers are never called."""
    import pyarrow.parquet as pq
    _capture["capsys"] = capsys
    reads, real_pd, real_pq = [], pd.read_parquet, pq.read_table

    def spy_pd(path, *a, **k):
        got = real_pd(path, *a, **k)
        reads.append(("pandas", str(path), k.get("columns"), k.get("filters"),
                      set(got.season) if "season" in got else None))
        return got

    def spy_pq(source, *a, **k):
        got = real_pq(source, *a, **k)
        reads.append(("pyarrow", str(getattr(source, "name", source)), k.get("columns"), k.get("filters"),
                      set(got.column("season").to_pylist()) if "season" in got.column_names else None))
        return got

    def engine_reader(*a, **k):
        raise AssertionError("the preflight called the engine's score reader")
    monkeypatch.setattr(pd, "read_parquet", spy_pd)
    monkeypatch.setattr(pq, "read_table", spy_pq)
    monkeypatch.setattr(outcomes, "nfl_games", engine_reader)
    monkeypatch.setattr(outcomes, "cfb_games", engine_reader)
    _preflight_on_made_up_tables(tmp_path, monkeypatch, "present")
    tables = [r for r in reads if r[1].endswith("games.parquet")]
    assert {r[1].split("/")[-4] for r in tables} == {"nfl-weather", "cfb-weather"}
    assert reads and all(r[2] is not None and not set(r[2]) & RESULT_COLS for r in reads), reads
    assert all(r[3] == outcomes.SEASON_FILTER and r[4] == {2024} for r in tables), tables
    # the spy sees the score columns when something does ask for them (the engine's reader, called directly)
    monkeypatch.undo()
    monkeypatch.setattr(pd, "read_parquet", spy_pd)
    reads.clear()
    outcomes.nfl_games(tmp_path / "present/repo/nfl-weather/data/processed/games.parquet")
    assert {"home_score", "away_score"} <= set(reads[0][2])
