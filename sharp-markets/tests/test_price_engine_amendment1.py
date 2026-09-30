"""Amendment 1 to the price engine's registration (sharp-markets/docs/PRICE_ENGINE_PREREGISTRATION.md, "Amendment
1"), item by item, on made-up input only. Nothing here is data."""
import math

import numpy as np
import pandas as pd
import pytest

from markets.research.price_engine import engine, model

NFL, CFB = model.NFL, model.CFB
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
