"""The Sep 29 independent audit (reviews/2026-09-29-astra-audit.md) listed what the suites did not
establish. One test per gap: board-level line sensitivity, no push on a half-point line, the primary
and secondary price labels, registered-version rejection, the test window's bounds, pre-kickoff entries,
the decision function, the frozen pricing cohort, and ledger coverage when forecasts are missing."""
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nflweather import board, runlog, weather  # noqa: E402
from nflweather.market import cohort_hash, cohort_residuals, ev_under, load_games, p_under_at, pricing_cohort  # noqa: E402

RESID = pricing_cohort()


# ------------------------------------------------------------------ the pricing model (D1)
def test_half_point_line_cannot_push():
    for line in (30.5, 44.5, 60.5):
        assert float(p_under_at(line, line, RESID)[1]) == 0.0


def test_whole_number_line_can_push_and_probabilities_add_up():
    win, push = (float(v) for v in p_under_at(44, 44, RESID))
    assert 0.01 < push < 0.06
    lose = 1 - float(p_under_at(44.5, 44, RESID)[0])       # loses above 44: the same as losing an under 44.5
    assert win + push + lose == pytest.approx(1.0)


def test_size_of_the_total_does_not_move_the_price():
    """Registered as flat: the cohort showed no dependence on the size of the total."""
    ev = [float(ev_under(L, -110, L, RESID)[0]) for L in (30.5, 44.5, 60.5)]
    assert ev[0] == ev[1] == ev[2]


def test_an_under_below_the_reference_is_worth_less_and_can_be_rejected():
    ev = [float(ev_under(44.5 + x, -115, 44.5, RESID)[0]) for x in (1, 0, -1, -3)]
    assert ev[0] > ev[1] > ev[2] > ev[3]
    assert ev[1] > 0 > ev[3]                                # at the reference it passes; 3 points below it fails


def test_board_prices_the_offered_line_against_the_reference():
    """Board wiring, the gap behind D1: the rule's own number is priced at the reference, and a better
    number at another book is priced higher against that same reference."""
    up = pd.DataFrame(dict(mkt_total=[44.5, 44.5, 60.5, np.nan], mkt_under=[-110.0, -110.0, -110.0, -110.0],
                           best_line=[45.5, 44.5, np.nan, 45.0], best_line_under=[-110.0, -105.0, np.nan, -110.0]))
    out = board.price(up, RESID)
    assert (out.ref_total.iloc[:3] == out.mkt_total.iloc[:3]).all()
    assert out.ev_best_line[0] > out.ev_under[0]            # a point more of line
    assert out.ev_best_line[1] > out.ev_under[1]            # same line, better price
    assert out.ev_under[0] == out.ev_under[2]               # flat in the size of the total
    assert np.isnan(out.ev_best_line[2]) and np.isnan(out.ev_under[3]) and np.isnan(out.ev_best_line[3])


def test_best_line_takes_the_highest_total_at_an_allowed_price():
    t = pd.DataFrame(dict(event_id=["e"] * 4, book=["pinnacle", "a", "b", "c"], total=[44.0, 45.0, 45.5, 45.0],
                          under_price=[-110, -112, -130, -105]))
    b = board.best_line(t).iloc[0]
    assert (b.best_line, b.best_line_under, b.best_line_book) == (45.0, -105, "c")   # 45.5 costs more than -115


def test_frozen_pricing_cohort():
    assert cohort_hash(RESID) == board.PRICING_COHORT_SHA256 and len(RESID) == 656
    hist = load_games(last=board.PRICING_LAST_SEASON)       # provenance: where the frozen file came from
    now = cohort_residuals(hist, (hist.outdoor == 1) & (hist.wx_wind >= board.RULE_B_WIND))
    assert cohort_hash(now) == board.PRICING_COHORT_SHA256, "games.parquet moved; the frozen file did not"


# ------------------------------------------------------------------ primary and secondary prices (D5)
def game(**kw):
    base = dict(wx_src="era5", wx_wind=18.0, lead_days=2, mkt_total=44.5, mkt_under=-110.0, ev_under=0.09)
    return SimpleNamespace(**(base | kw))


def test_price_source_labels_the_signal():
    assert board.rule_b_status(game(line_src="pinnacle")) == "SIGNAL"
    assert board.rule_b_status(game(line_src="nflverse")) == "SIGNAL_SECONDARY"
    assert board.rule_b_status(game(line_src="nflverse", mkt_under=-130.0)) == "price_too_high"


# ------------------------------------------------------------------ the scorer (D2)
ROW = dict(rules_version="v3-2026-09-28", gameday="2026-10-11", gametime="13:00", away_team="A", home_team="B",
           lead_days=3, wx_src="era5", wx_wind=16, wx_temp=60, wx_precip=0, wx_snow=0, line_src="pinnacle",
           total_line=44, under_odds=-110, over_odds=-110, p_under=0.54, p_market=0.5, lean="", ev_under=0.08,
           rule_b="SIGNAL", snapshot_utc="2026-10-08T15:00:00Z")
GAME = dict(total=40, total_line=42, gameday="2026-10-11", gametime="13:00", result=3)


def score(tmp_path, rows, games):
    pd.DataFrame(rows).to_csv(tmp_path / "ledger.csv", index=False)
    pd.DataFrame(games).to_csv(tmp_path / "games.csv", index=False)
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "score_forward.py"), "--ledger",
                           str(tmp_path / "ledger.csv"), "--games", str(tmp_path / "games.csv")],
                          capture_output=True, text=True, check=True).stdout


def test_scorer_counts_only_registered_pre_kickoff_rows_inside_the_window(tmp_path):
    rows = [dict(ROW, game_id="OK"),
            dict(ROW, game_id="BADVER", rules_version="NOT_REGISTERED"),
            dict(ROW, game_id="LATE", snapshot_utc="2026-10-11T18:00:00Z"),                  # after kickoff
            dict(ROW, game_id="Y2028", gameday="2028-10-08", snapshot_utc="2028-10-05T15:00:00Z"),
            dict(ROW, game_id="WEEK4", gameday="2026-10-04", snapshot_utc="2026-10-02T15:00:00Z")]
    games = [dict(GAME, game_id=r["game_id"], gameday=r["gameday"]) for r in rows]
    out = score(tmp_path, rows, games)
    assert "ledger rows: 5; in the test: 1" in out
    for reason in ("unregistered rules version: 1", "logged at or after kickoff: 1", "after the 2027 season: 1",
                   "before Week 5 (Oct 8, 2026): 1"):
        assert reason in out
    assert "RULE_B (wind under): 1 signals, 1 settled" in out


def test_secondary_price_is_reported_apart_and_left_out_of_the_decision(tmp_path):
    rows = [dict(ROW, game_id="PIN"),
            dict(ROW, game_id="BACKUP", line_src="nflverse", rule_b="SIGNAL_SECONDARY"),
            dict(ROW, game_id="OLDV2", line_src="nflverse", rules_version="v2-2026-09-28")]   # v2 wrote SIGNAL
    out = score(tmp_path, rows, [dict(GAME, game_id=r["game_id"]) for r in rows])
    assert "RULE_B (wind under): 1 signals, 1 settled" in out
    assert "RULE_B, secondary price (not part of the decision): 2 signals, 2 settled" in out
    assert out.count("decision (Rule B") == 1


def test_decision_is_interim_until_the_horizon_and_applies_every_criterion(tmp_path):
    rows = [dict(ROW, game_id=f"G{i}", total_line=44 + (i % 3)) for i in range(6)]
    games = [dict(GAME, game_id=f"G{i}", total_line=42) for i in range(6)]
    out = score(tmp_path, rows, games)
    assert "INTERIM read, decides nothing" in out and "FINAL" not in out.split("Decision horizons")[0]
    assert "win rate vs the close" in out and "mean CLV by season" in out


def test_forty_signals_make_the_decision_final(tmp_path):
    rows = [dict(ROW, game_id=f"G{i}", total_line=44 + (i % 3)) for i in range(40)]
    games = [dict(GAME, game_id=f"G{i}", total_line=42, week=5 + (i % 12)) for i in range(40)]
    out = score(tmp_path, rows, games)
    assert "FINAL: KEEP" in out and "mean CLV by half" in out       # one season: both halves must be positive


# ------------------------------------------------------------------ log, don't drop (D6) and provenance
def test_no_forecasts_still_gives_a_frame_the_board_can_merge(monkeypatch):
    monkeypatch.setattr(weather, "load_hourly", lambda *a, **k: None)
    g = pd.DataFrame([dict(game_id="G1", roof="outdoors", stadium_id="BUF00", stadium="x", gameday="2026-10-11",
                           gametime="13:00")])
    w = weather.game_weather(g, kind="forecast")
    assert w.empty and list(w.columns) == ["game_id", *weather.WEATHER_COLS]
    assert g.merge(w, on="game_id", how="left").om_wind.isna().all()


def test_a_run_always_leaves_a_record(tmp_path):
    runlog.record_run(tmp_path / "runs.csv", "nfl-alerts", "v3", "failed", error="ConnectionError: down\nretry")
    runlog.record_run(tmp_path / "runs.csv", "nfl-alerts", "v3", "ok", games=14, signals=1, priced=11, unmapped="X")
    r = pd.read_csv(tmp_path / "runs.csv")
    assert list(r.columns) == runlog.RUN_COLS and list(r.status) == ["failed", "ok"]
    assert r.error[0] == "ConnectionError: down retry" and r.games[1] == 14


def test_forecast_is_kept_under_its_content_hash(tmp_path):
    f = tmp_path / "BUF00_2026-10-11.json"
    f.write_text('{"hourly": {"time": []}}')
    h, fetched = runlog.keep_forecast(f, tmp_path / "kept")
    assert len(h) == 16 and fetched.endswith("Z") and (tmp_path / "kept" / f"{h}.json.gz").exists()
    assert runlog.keep_forecast(f)[0] == h                           # hash only, no archive
    assert runlog.keep_forecast(tmp_path / "missing.json") == ("", "")
    f.write_text('{"hourly": {"time": ["x"]}}')
    assert runlog.keep_forecast(f)[0] != h


def test_shared_copies_match():
    cfb = ROOT.parent / "cfb-weather" / "cfbweather"
    for name in ("quota.py", "runlog.py"):
        a = (ROOT / "nflweather" / name).read_text().split("\n", 1)[1]
        b = (cfb / name).read_text().split("\n", 1)[1]
        assert a == b, name

    def pricing(p):
        s = p.read_text()
        return s[s.index("def cohort_residuals"):s.index("# ---", s.index("def ev_under"))]
    assert pricing(ROOT / "nflweather" / "market.py") == pricing(cfb / "market.py")


def test_close_capture_counts_as_a_scheduled_job(monkeypatch):
    from nflweather import quota
    for label, want in (("com.nflweather.alerts", True), ("com.valuefinder.closecapture", True),
                        ("com.valuefinder.triggerpoll", False), ("", False)):
        monkeypatch.setenv("XPC_SERVICE_NAME", label)
        assert quota.scheduled() is want


def test_crosswind_is_the_part_of_the_wind_across_the_field():
    cross, along = board.wind_components([20, 20, 20, 20], [0, 90, 45, 270], [0, 0, 0, 90])
    assert cross == pytest.approx([0, 20, 20 * 0.5 ** 0.5, 0], abs=1e-9)
    assert along == pytest.approx([20, 0, 20 * 0.5 ** 0.5, 20], abs=1e-9)
    c, a = board.wind_components([20], [np.nan], [10])
    assert np.isnan(c[0]) and np.isnan(a[0])
    heads = pd.read_csv(ROOT / "data" / "processed" / "stadium_headings.csv")
    assert heads.stadium_id.is_unique and heads.heading.between(0, 360).all() and len(heads) > 60
    assert not heads[heads.use].second_source_gap_deg.gt(15).any()   # used only where the two sources agree
    assert not heads[heads.second_source_gap_deg > 15].use.any()
