"""Amendment 1 to the price engine's registration (sharp-markets/docs/PRICE_ENGINE_PREREGISTRATION.md, "Amendment
1"), item by item, on made-up input only. Nothing here is data."""
import math
from collections import Counter

import numpy as np
import pandas as pd
import pytest

from markets.oddsapi import bulk
from markets.research.price_engine import engine, fixture, model, outcomes
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
    monkeypatch.setattr(pf.o, "nfl_games", lambda: nfl)
    monkeypatch.setattr(pf.o, "cfb_games", lambda: cfb)
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

    from markets.research.price_engine import quotes
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
