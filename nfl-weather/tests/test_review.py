"""The review of the audit fixes (pull request 50) found places where the new code still fell short of
amendment 5. One test per finding: the decision horizons, a bet with no close, the best line for games
Pinnacle doesn't quote, a Pinnacle total with no under price, prices that aren't prices, quarter-point
lines, the cohort check on the live path, the ledger rewrite, and a run that fails after the board."""
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nflweather import board, config, market, notify, oddsapi, runlog  # noqa: E402
from nflweather.market import american_to_profit, ev_under, p_under_at, pricing_cohort, valid_odds  # noqa: E402

RESID = pricing_cohort(board.PRICING_COHORT_SHA256)


# ------------------------------------------------------------------ the scorer's decisions
def season(year, weeks, n, first_id=0, line=44, close=42, total=40, lean=""):
    """`n` Rule B signals (or leans) spread over `weeks` of a season, as ledger rows and schedule rows."""
    start = pd.Timestamp(f"{year}-09-10")                      # Week 1 Thursday, near enough
    rows, games = [], []
    for i in range(n):
        wk = weeks[i % len(weeks)]
        day = (start + pd.Timedelta(weeks=wk - 1, days=3)).strftime("%Y-%m-%d")
        gid = f"{year}_{wk:02d}_{first_id + i}"
        rows.append(dict(rules_version="v3-2026-09-28", game_id=gid, gameday=day, gametime="13:00", away_team="A",
                         home_team="B", lead_days=3, wx_src="era5", wx_wind=16, line_src="pinnacle", total_line=line,
                         under_odds=-110, over_odds=-110, p_under=0.56, p_market=0.5, lean=lean, ev_under=0.08,
                         rule_b="" if lean else "SIGNAL",
                         snapshot_utc=(pd.Timestamp(day) - pd.Timedelta(days=3)).strftime("%Y-%m-%dT15:00:00Z")))
        games.append(dict(game_id=gid, season=year, week=wk, game_type="REG", gameday=day, gametime="13:00",
                          total=total, total_line=close, result=3))
    return rows, games


def unplayed(year, week=18):
    day = (pd.Timestamp(f"{year}-09-10") + pd.Timedelta(weeks=week - 1, days=3)).strftime("%Y-%m-%d")
    return dict(game_id=f"{year}_{week}_LAST", season=year, week=week, game_type="REG", gameday=day,
                gametime="13:00", total=np.nan, total_line=45, result=np.nan)


def score(tmp_path, rows, games, now):
    pd.DataFrame(rows).to_csv(tmp_path / "ledger.csv", index=False)
    pd.DataFrame(games).to_csv(tmp_path / "games.csv", index=False)
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "score_forward.py"), "--ledger",
                           str(tmp_path / "ledger.csv"), "--games", str(tmp_path / "games.csv"), "--now", now],
                          capture_output=True, text=True, check=True).stdout


def rule_b(out):
    return out.split("RULE_B (wind under)")[1].split("RULE_B, secondary")[0]


def test_forty_signals_in_2026_wait_for_week_18(tmp_path):
    rows, games = season(2026, range(5, 15), 40)
    out = rule_b(score(tmp_path, rows, games + [unplayed(2026)], "2026-12-20"))
    assert "INTERIM read, decides nothing" in out and "FINAL" not in out
    played = dict(unplayed(2026), total=40, result=3)
    out = rule_b(score(tmp_path, rows, games + [played], "2027-01-12"))
    assert "decided after Week 18 of 2026), FINAL: KEEP" in out and "mean CLV by half" in out and "n=40" in out


def test_a_final_decision_does_not_move_when_later_bets_arrive(tmp_path):
    rows, games = season(2026, range(5, 19), 40)
    first = rule_b(score(tmp_path, rows, games, "2027-01-20"))
    more, more_games = season(2027, range(1, 6), 5, first_id=100, line=30, close=42)     # five bad bets in 2027
    later = rule_b(score(tmp_path, rows + more, games + more_games + [unplayed(2027)], "2027-10-20"))
    pick = lambda out: [ln for ln in out.splitlines() if "decision (" in ln or "mean CLV +" in ln and "n=" in ln]  # noqa: E731
    assert "FINAL: KEEP" in first and pick(first) == pick(later)


def test_fewer_than_forty_in_2026_wait_for_the_end_of_2027(tmp_path):
    a, ga = season(2026, range(5, 19), 25)
    b, gb = season(2027, range(1, 10), 15, first_id=100)
    out = rule_b(score(tmp_path, a + b, ga + gb + [unplayed(2027)], "2027-11-15"))      # 40 settled, season unfinished
    assert "INTERIM read, decides nothing" in out and "FINAL" not in out
    done = dict(unplayed(2027), total=40, result=3)
    out = rule_b(score(tmp_path, a + b, ga + gb + [done], "2028-01-12"))
    assert "both seasons pooled), FINAL: KEEP" in out and "mean CLV by season" in out and "n=40" in out


def test_an_interim_read_prints_no_verdict(tmp_path):
    rows, games = season(2026, range(5, 8), 3)
    out = rule_b(score(tmp_path, rows, games + [unplayed(2026)], "2026-11-01"))
    line = next(ln for ln in out.splitlines() if "decision (" in ln)
    assert "INTERIM read, decides nothing" in line
    assert not any(word in line for word in ("KEEP", "DROP", "INCONCLUSIVE"))


def test_model_lean_counts_and_decides_on_the_same_bets(tmp_path):
    a, ga = season(2026, range(5, 19), 25, lean="UNDER lean")
    b, gb = season(2027, range(1, 10), 15, first_id=100, lean="UNDER lean")
    out = score(tmp_path, a + b, ga + gb + [unplayed(2027)], "2027-11-15").split("RULE_B (wind under)")[0]
    assert "MODEL_LEAN: 40 signals, 40 settled" in out
    assert "INTERIM read, decides nothing" in out and "FINAL" not in out       # 25 leans in 2026 decide nothing


def test_a_bet_with_no_close_is_not_a_loss_against_the_close(tmp_path):
    rows, games = season(2026, range(5, 9), 4)
    games[3]["total_line"] = np.nan
    out = rule_b(score(tmp_path, rows, games + [unplayed(2026)], "2026-11-15"))
    assert "3 of 4 bets have a primary close" in out
    # amendment 6 (the review's m9): one meaning of "with a primary close" per printout
    assert "win rate vs the close 100.0% (3 of the 3 bets that have a primary close and didn't tie it; 0 ties" in out


def test_keep_and_drop_both_met_is_a_drop(tmp_path):
    """The whole interval between 0 and +0.25 meets the keep test and the drop test. Registered: drop."""
    rows, games = season(2026, range(5, 19), 40, line=42.1, close=42)
    for i, r in enumerate(rows):
        r["total_line"] = 42.1 + 0.01 * (i % 2)
    out = rule_b(score(tmp_path, rows, games, "2027-01-20"))
    assert "FINAL: DROP" in out and "upper bound is below +0.25 (met)" in out


def test_excluded_rows_can_be_listed(tmp_path):
    rows, games = season(2026, range(5, 7), 2)
    rows[1]["rules_version"] = "NOT_REGISTERED"
    pd.DataFrame(rows).to_csv(tmp_path / "ledger.csv", index=False)
    pd.DataFrame(games).to_csv(tmp_path / "games.csv", index=False)
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "score_forward.py"), "--ledger",
                          str(tmp_path / "ledger.csv"), "--games", str(tmp_path / "games.csv"), "--list-excluded"],
                         capture_output=True, text=True, check=True).stdout
    assert "excluded, unregistered rules version: 1" in out and rows[1]["game_id"] in out.split("MODEL_LEAN")[0]


# ------------------------------------------------------------------ the odds feed and the two prices
def feed(event, book, total, under, home="BUF", away="NE"):
    return dict(snapshot_utc="2026-10-09T1430Z", event_id=event, commence_utc="2026-10-11T17:00:00Z", home=home,
                away=away, home_name=home, away_name=away, book=book, market="totals", total=total, over_price=-110,
                under_price=under, book_update="2026-10-09T14:28:00Z")


def test_best_line_is_logged_for_a_game_pinnacle_does_not_quote(monkeypatch):
    rows = [feed("e1", "pinnacle", 44.5, -108), feed("e1", "fanduel", 45.5, -110),
            feed("e2", "fanduel", 39.5, -110, "MIN", "MIA"), feed("e2", "draftkings", 38.5, -105, "MIN", "MIA")]
    monkeypatch.setattr(oddsapi, "live", lambda **k: pd.DataFrame(rows))
    pin = board._pinnacle_live().set_index("home_team")
    assert pin.loc["BUF", ["pin_total", "best_line", "best_line_book"]].tolist() == [44.5, 45.5, "fanduel"]
    assert np.isnan(pin.loc["MIN", "pin_total"])
    assert pin.loc["MIN", ["best_line", "best_line_under", "best_line_book"]].tolist() == [39.5, -110, "fanduel"]
    assert pin.loc["MIN", "quote_utc"] == "2026-10-09T14:30:00Z"            # one format, with seconds

    up = pd.DataFrame(dict(home_team=["BUF", "MIN", "DAL"], away_team=["NE", "MIA", "NYG"], gameday="2026-10-11",
                           total_line=[44.0, 38.5, 47.0], under_odds=-110.0, over_odds=-110.0))
    out = board.price(board.use_pinnacle(up, pin.reset_index()), RESID).set_index("home_team")
    assert out.line_src.to_dict() == {"BUF": "pinnacle", "MIN": "nflverse", "DAL": "nflverse"}
    assert out.loc["MIN", "best_line"] == 39.5 and out.loc["MIN", "ev_best_line"] > out.loc["MIN", "ev_under"]
    assert np.isnan(out.loc["DAL", "best_line"]) and out.loc["DAL", "quote_utc"] == ""


def test_a_pinnacle_total_with_no_under_price_leaves_the_backup_price():
    pin = pd.DataFrame(dict(home_team=["BUF"], away_team=["NE"], gameday="2026-10-11", pin_total=[48.5],
                            pin_over=[-105.0], pin_under=[np.nan], best_under=np.nan, best_under_book="",
                            best_line=48.5, best_line_under=-110.0, best_line_book="fanduel", quote_utc="q",
                            quote_update="u"))
    up = pd.DataFrame(dict(home_team=["BUF"], away_team=["NE"], gameday="2026-10-11", total_line=[48.0],
                           under_odds=[-110.0], over_odds=[-110.0]))
    r = board.price(board.use_pinnacle(up, pin), RESID).iloc[0]
    assert (r.line_src, r.mkt_total, r.mkt_under) == ("nflverse", 48.0, -110.0)
    status = board.rule_b_status(SimpleNamespace(wx_src="era5", wx_wind=18.0, lead_days=2, **r[
        ["mkt_total", "mkt_under", "ev_under", "line_src"]].to_dict()))
    assert status == "SIGNAL_SECONDARY"


# ------------------------------------------------------------------ the pricing model
@pytest.mark.parametrize("odds", [0, -50, 99, -99, 1.91, None, float("nan"), "x"])
def test_a_number_that_is_not_a_price_is_no_price(odds):
    assert not valid_odds(odds) and np.isnan(american_to_profit(odds)).all()
    assert np.isnan(ev_under(44.5, odds, 44.5, RESID)).all()
    r = SimpleNamespace(wx_src="era5", wx_wind=18.0, lead_days=2, mkt_total=44.5, mkt_under=odds, ev_under=np.nan,
                        line_src="pinnacle")
    assert board.rule_b_status(r) == "no_price"


def test_real_prices_still_price():
    assert american_to_profit([100, 105, -115]).tolist() == pytest.approx([1.0, 1.05, 100 / 115])
    assert valid_odds(-115) and valid_odds(100)
    assert float(ev_under(44.5, -115, 44.5, RESID)[0]) == pytest.approx(0.0744, abs=5e-4)     # as registered


def test_missing_inputs_price_as_missing_whatever_their_type():
    for line, odds, ref in ((pd.NA, -110, 44.5), (44.5, -110, None), (None, None, None)):
        out = ev_under(line, odds, ref, RESID)
        assert out.shape == (1,) and np.isnan(out[0])


def test_a_higher_line_is_never_worth_less_on_the_quarter_point_grid():
    for ref in (38.5, 41.0, 44.0, 47.5, 55.0):
        lines = np.arange(ref - 20, ref + 20.01, 0.25)
        win, push = p_under_at(lines, np.full(len(lines), ref), RESID)
        assert (np.diff(win) >= -1e-12).all() and (np.diff(1 - win - push) <= 1e-12).all()
    w, p = (float(v) for v in p_under_at(43.75, 44, RESID))            # half a bet at 43.5, half at 44
    a, b = p_under_at(43.5, 44, RESID), p_under_at(44, 44, RESID)
    assert w == pytest.approx((float(a[0]) + float(b[0])) / 2) and p == pytest.approx(float(b[1]) / 2)
    assert float(p_under_at(44 - 1e-12, 44, RESID)[1]) == float(b[1])   # float noise doesn't turn 44 into 43.5


def test_the_live_path_refuses_a_cohort_that_was_not_registered(tmp_path, monkeypatch):
    import json
    js = json.loads((config.PROC / "pricing_cohort.json").read_text())
    js["residuals"] = [r - 5 for r in js["residuals"]]
    (tmp_path / "pricing_cohort.json").write_text(json.dumps(js))
    monkeypatch.setattr(market, "PROC", tmp_path)
    with pytest.raises(ValueError, match="not the registered cohort"):
        pricing_cohort(board.PRICING_COHORT_SHA256)


# ------------------------------------------------------------------ records
def test_widening_the_ledger_leaves_old_rows_exactly_as_written(tmp_path):
    path = tmp_path / "ledger.csv"
    old = ("snapshot_utc,game_id,ev_under,wx_precip,note\n"
           "2026-09-28T17:44:00Z,2026_04_NE_BUF,0.12757973733583483,0.036000000000000004,\n"
           "2026-09-28T21:30:00Z,2026_04_NE_BUF,0.48550223122466146,,kept\n")
    path.write_text(old)
    snap = pd.DataFrame(dict(snapshot_utc=["2026-09-29T14:30:00Z"], rules_version=["v3-2026-09-28"],
                             game_id=["2026_04_NE_BUF"], ev_under=[0.0744], wx_precip=[np.nan], best_line=[45.5]))
    board.widen_ledger(path, snap)
    new = pd.read_csv(path, dtype=str, keep_default_na=False)
    assert list(new.columns) == ["snapshot_utc", "rules_version", "game_id", "ev_under", "wx_precip", "best_line", "note"]
    assert new.ev_under.tolist() == ["0.12757973733583483", "0.48550223122466146", "0.0744"]
    assert new.wx_precip.tolist() == ["0.036000000000000004", "", ""] and new.note.tolist() == ["", "kept", ""]
    assert (tmp_path / "ledger.before-v3-2026-09-28.csv").read_text() == old and not (tmp_path / "ledger.csv.tmp").exists()


def test_a_bad_headings_table_cannot_cost_the_run(tmp_path):
    up = pd.DataFrame(dict(om_wind_dir=[270.0], wx_wind=[20.0], stadium_id=["BUF00"]))
    out = board.add_crosswind(up.copy(), tmp_path / "missing.csv")
    assert out.wx_cross.isna().all() and out.wx_along.isna().all() and out.wx_wind_dir.tolist() == [270.0]
    (tmp_path / "h.csv").write_text("stadium_id,heading,use\nBUF00,0,\nBUF00,90,True\nBUF00,90,True\n")
    out = board.add_crosswind(up.copy(), tmp_path / "h.csv")               # a blank flag and a repeated row
    assert out.wx_cross.tolist() == pytest.approx([0.0], abs=1e-9) and out.wx_along.tolist() == pytest.approx([20.0])


def test_keys_never_reach_the_run_record(tmp_path):
    err = "HTTPError: 401 for url: https://api.the-odds-api.com/v4/x/odds?apiKey=abc123def&regions=us"
    assert "abc123def" not in runlog.scrub(err) and "apiKey=***&regions=us" in runlog.scrub(err)
    runlog.record_run(tmp_path / "runs.csv", "nfl-alerts", "v3", "failed", error=err)
    assert "abc123def" not in (tmp_path / "runs.csv").read_text()


# ------------------------------------------------------------------ the alert run, end to end and offline
BOARD = dict(game_id="2026_06_NE_BUF", away_team="NE", home_team="BUF", gameday="2030-10-13", gametime="13:00",
             conditions="18 mph, 50°F", lead_days=2, wx_src="era5", wx_wind=18.0, wx_temp=50.0, wx_precip=0.0,
             wx_snow=0.0, line_src="pinnacle", mkt_total=44.5, mkt_under=-108.0, ev_under=0.09, rule_b="SIGNAL",
             best_under=np.nan, best_under_book="", best_line=45.5, best_line_under=-110.0, best_line_book="fanduel",
             ev_best_line=0.12, lean="", p_under=0.5, p_market=0.5, edge=0.0, v_dome=0, v_city_temp7=50.0,
             spread_line=3.0)


def run_alerts(tmp_path, monkeypatch, up, save=None):
    sent = []
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(board, "compute", up if callable(up) else (lambda **k: up))
    monkeypatch.setattr(board, "save", save or (lambda up: None))
    monkeypatch.setattr(oddsapi, "has_key", lambda: False)
    monkeypatch.setattr(notify, "send", lambda title, body: sent.append((title, body)) or True)
    monkeypatch.setattr(sys, "argv", ["alerts.py"])
    error = None
    try:
        runpy.run_path(str(ROOT / "scripts" / "alerts.py"), run_name="__main__")
    except BaseException as e:
        error = e
    runs = pd.read_csv(tmp_path / "data" / "forward" / "runs.csv", keep_default_na=False)
    return sent, runs, error


def test_a_finished_run_is_recorded_once_at_the_end(tmp_path, monkeypatch):
    sent, runs, error = run_alerts(tmp_path, monkeypatch, pd.DataFrame([BOARD]))
    assert error is None and runs.status.tolist() == ["ok"] and runs.signals.tolist() == [1]
    assert len(sent) == 1 and sent[0][0].startswith("RULE B WIND UNDER 44.5 at -108")
    assert "Best number: under 45.5 at -110 (fanduel)" in sent[0][1]


def test_the_highest_number_is_named_only_when_it_is_worth_more(tmp_path, monkeypatch):
    sent, _, _ = run_alerts(tmp_path, monkeypatch, pd.DataFrame([dict(BOARD, ev_best_line=0.05)]))
    assert len(sent) == 1 and "Best number" not in sent[0][1]


def failed(error):
    """A failed run exits with status 1 after printing the error with any key blanked (it no longer
    re-raises the original exception, whose text could hold a key)."""
    return isinstance(error, SystemExit) and error.code == 1


def test_a_run_that_fails_while_saving_is_recorded_and_notified(tmp_path, monkeypatch):
    def full(up):
        raise OSError(28, "No space left on device")
    sent, runs, error = run_alerts(tmp_path, monkeypatch, pd.DataFrame([BOARD]), save=full)
    assert failed(error)
    assert runs.status.tolist() == ["failed"] and runs.games.tolist() == [1]
    assert runs.error[0].startswith("while saving the ledger: OSError")
    assert [t for t, _ in sent] == ["NFL weather alerts: run failed"]


def test_a_failed_download_is_recorded_without_the_key(tmp_path, monkeypatch):
    def down(**k):
        raise ConnectionError("GET https://api.the-odds-api.com/v4/odds?apiKey=SECRETKEY123 failed")
    sent, runs, error = run_alerts(tmp_path, monkeypatch, down)
    assert failed(error) and runs.status.tolist() == ["failed"]
    assert runs.error[0].startswith("while building the board: ConnectionError")
    assert "SECRETKEY123" not in runs.error[0] and "SECRETKEY123" not in sent[0][1]


def test_one_games_alert_cannot_cost_the_others_theirs(tmp_path, monkeypatch):
    bad = dict(BOARD, game_id="2026_06_MIA_NYJ", home_team="NYJ", away_team="MIA", wx_precip="not a number")
    sent, runs, error = run_alerts(tmp_path, monkeypatch, pd.DataFrame([bad, BOARD]))
    assert [t for t, _ in sent][0].startswith("RULE B WIND UNDER 44.5 at -108: NE @ BUF")
    assert failed(error) and runs.status.tolist() == ["failed"]
    assert runs.error[0].startswith("while building the alerts: RuntimeError: 1 game(s) raised: MIA @ NYJ")
    assert sent[-1][0] == "NFL weather alerts: run failed"


def test_shared_price_helpers_match():
    cfb = ROOT.parent / "cfb-weather" / "cfbweather" / "market.py"

    def helpers(p):
        s = p.read_text()
        return s[s.index("def _num"):s.index("def american_to_prob")]
    assert helpers(ROOT / "nflweather" / "market.py") == helpers(cfb)
