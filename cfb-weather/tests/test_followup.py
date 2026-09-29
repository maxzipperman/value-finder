"""The follow-up review of pull request 50 (the audit fixes) found smaller problems in the live alert path,
the run records and the price helpers. One test per finding, named by its id in the review: the trigger
poller on the widened ledger (L1, the one the owner installs on Oct 1), games priced at a rule book in the
run record (L3), one board row per game (L5), a failed run's printout (L6), the alert state saved after
each send (L7) and a damaged state file (L8), valid_odds on a one-row frame (P6) and the forecast replay's
prices (P8). runlog.py and the price helpers are shared with nfl-weather, whose tests cover them in full."""
import json
import runpy
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cfbweather import board, config, fetch, live, notify  # noqa: E402
from cfbweather.market import ev_under, p_under_at, pricing_cohort, valid_odds  # noqa: E402

RESID = pricing_cohort(board.PRICING_COHORT_SHA256)
KEY = "0123456789abcdef0123456789abcdef"            # a made-up key, 32 hex characters like the real one
NAMES = {"Wyoming Cowboys": "Wyoming", "Air Force Falcons": "Air Force"}


# ------------------------------------------------------------------ L1: the trigger poller on the widened ledger
V3 = ("snapshot_utc,rules_version,game_id,kick_et,away_team,home_team,venue,lead_days,wx_src,wx_wind,wx_temp,"
      "wx_precip,line_src,mkt_total,mkt_under,mkt_over,ev_under,rule_b,best_under,best_under_book,ht_threshold,rule_ht,"
      "ref_total,best_line,best_line_under,best_line_book,ev_best_line,quote_utc,quote_update,wx_hash,wx_fetched_utc,"
      "wx_wind_dir,start_utc").split(",")                                 # the ledger's columns since amendment 3


def book(key, point, under, stamp="2026-10-09T15:58:00Z"):
    outs = [dict(name="Over", price=-110, point=point), dict(name="Under", price=under, point=point)]
    return dict(key=key, markets=[dict(key="totals", last_update=stamp, outcomes=outs)])


def event(books, eid="e1", kick="2026-10-10T19:00:00Z"):
    return dict(id=eid, home_team="Wyoming Cowboys", away_team="Air Force Falcons", commence_time=kick,
                bookmakers=books)


@pytest.mark.parametrize("cols", [V3, ["snapshot_utc", "rules_version"] + board.COLS + ["start_utc"]])
def test_L1_the_trigger_poller_reads_the_widened_ledger(tmp_path, cols):
    """It crashed (KeyError: quote_utc) on every ledger written since amendment 3; the job goes in on Oct 1."""
    row = dict.fromkeys(cols, "") | dict(snapshot_utc="2026-10-09T12:30:00Z", rules_version=board.RULES_VERSION,
                                         game_id=1, away_team="Air Force", home_team="Wyoming", lead_days=1,
                                         wx_wind=17.5, rule_b="no_price", start_utc="2026-10-10 19:00:00+00:00",
                                         quote_utc="2026-10-09T12:29:58Z", quote_update="2026-10-09T12:20:00Z")
    pd.DataFrame([row], columns=cols).to_csv(tmp_path / "ledger.csv", index=False)
    ledger = pd.read_csv(tmp_path / "ledger.csv")                  # as scripts/poll_triggers.py reads it
    active = live.active_triggers(ledger, pd.Timestamp("2026-10-09T16:00:00Z"))
    quotes = live.book_rows([event([book("pinnacle", 44.5, -108), book("bovada", 44.5, -105)])], NAMES,
                            "2026-10-09T16:00:00Z")
    r = live.trigger_rows(active, quotes, "2026-10-09T16:00:05Z")
    assert list(r.book) == ["pinnacle", "bovada"] and list(r.under_price) == [-108, -105]
    assert set(r.ledger_snapshot_utc) == {"2026-10-09T12:30:00Z"} and set(r.quote_utc) == {"2026-10-09T16:00:00Z"}
    assert r.iloc[0].kick_utc == "2026-10-10T19:00:00Z" and r.iloc[0].wx_wind == 17.5 and r.sealed.all()


# ------------------------------------------------------------------ the alert run, offline
def board_row(**kw):
    kick = pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=2)
    base = dict(game_id=401, away_team="Southern Miss", home_team="Troy", kick_et="Tue 10-06 20:00", lead_days=2,
                start_utc=kick, wx_wind=18.0, wx_temp=55.0, line_src="pinnacle", mkt_total=50.5, mkt_under=-110.0,
                ev_under=0.08, rule_b="SIGNAL", rule_ht="below_threshold", ht_threshold=62.6175, best_under=np.nan,
                best_under_book="", best_line=np.nan, best_line_under=np.nan, best_line_book="", ev_best_line=np.nan)
    return base | kw


OTHER = dict(game_id=402, home_team="Army", away_team="Navy")


def run_alerts(tmp_path, monkeypatch, rows, state=None, send=None, save=None, compute=None):
    """One run of scripts/alerts.py with everything under tmp_path: (sent, runs, exit status, saved state)."""
    sent, fwd = [], tmp_path / "data" / "forward"
    fwd.mkdir(parents=True, exist_ok=True)
    if state is not None:
        (fwd / "alert_state.json").write_text(state if isinstance(state, str) else json.dumps(state))
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(board, "compute", compute or (lambda **k: pd.DataFrame(rows)))
    monkeypatch.setattr(board, "save", save or (lambda up: None))
    monkeypatch.setattr(notify, "send", send or (lambda title, body: sent.append((title, body)) or True))
    monkeypatch.setattr(sys, "argv", ["alerts.py"])
    code = 0
    try:
        runpy.run_path(str(ROOT / "scripts" / "alerts.py"), run_name="__main__")
    except SystemExit as e:
        code = e.code
    runs = pd.read_csv(fwd / "runs.csv", keep_default_na=False) if (fwd / "runs.csv").exists() else None
    saved = json.loads((fwd / "alert_state.json").read_text()) if (fwd / "alert_state.json").exists() else None
    return sent, runs, code, saved


def test_L3_the_run_record_counts_games_priced_at_a_rule_book(tmp_path, monkeypatch):
    rows = [board_row(game_id=g, line_src=src, rule_b="no_trigger") for g, src in
            ((1, "pinnacle"), (2, "draftkings"), (3, "DraftKings"), (4, ""))]        # 3: ESPN's backup price
    _, runs, code, _ = run_alerts(tmp_path, monkeypatch, rows)
    assert code == 0 and runs.columns[-1] == "rule_priced"
    assert runs[["games", "priced", "rule_priced"]].values.tolist() == [[4, 4, 2]]


def test_L6_a_failed_run_prints_the_error_without_the_key_and_exits_1(tmp_path, monkeypatch, capsys):
    def down(**k):
        raise ConnectionError(f"GET https://api.the-odds-api.com/v4/odds?apiKey={KEY}&markets=totals failed")
    _, runs, code, _ = run_alerts(tmp_path, monkeypatch, [], compute=down)
    out = capsys.readouterr()
    assert code == 1 and runs.status.tolist() == ["failed"] and KEY not in out.out + out.err
    assert "run failed while building the board: ConnectionError" in out.out and "Traceback" not in out.err


def test_L7_a_send_that_fails_part_way_is_not_repeated_next_run(tmp_path, monkeypatch):
    calls = []

    def flaky(title, body):
        calls.append(title)
        if len(calls) == 2:
            raise ConnectionError("ntfy unreachable")
        return True
    rows = [board_row(), board_row(**OTHER)]
    _, runs, code, saved = run_alerts(tmp_path, monkeypatch, rows, send=flaky)
    assert code == 1 and runs.error[0].startswith("while sending the alerts: ConnectionError")
    assert saved["401"]["sent"] == ["ruleb"] and saved["402"]["sent"] == []
    sent, runs, code, _ = run_alerts(tmp_path, monkeypatch, rows)
    assert code == 0 and [t for t, _ in sent] == [calls[1]]     # only the one that didn't go out


def test_L7_a_state_file_that_cannot_be_written_does_not_stop_the_alerts(tmp_path, monkeypatch):
    from cfbweather import runlog

    def full(path, state):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(runlog, "write_alert_state", full)
    sent, runs, code, _ = run_alerts(tmp_path, monkeypatch, [board_row(), board_row(**OTHER)])
    assert [t.split(": ")[1][:11] for t, _ in sent[:2]] == ["Southern Mi", "Navy @ Army"]      # both went out
    assert code == 1 and runs.error[0].startswith("while saving the alert state: RuntimeError: alert_state.json "
                                                  "could not be saved (OSError")


def test_L8_a_damaged_state_file_costs_no_ledger_row(tmp_path, monkeypatch):
    saved_boards = []
    sent, runs, code, saved = run_alerts(tmp_path, monkeypatch, [board_row()], state='{"401": {"sent": ["ru',
                                         save=saved_boards.append)
    fwd = tmp_path / "data" / "forward"
    assert code == 0 and len(saved_boards) == 1 and len(sent) == 1
    assert runs.status.tolist() == ["ok"] and runs.error[0].startswith("alert_state.json could not be read")
    (copy,) = fwd.glob("alert_state.corrupt-*.json")
    assert copy.read_text() == '{"401": {"sent": ["ru' and saved == {"401": {"sent": ["ruleb"]}}


# ------------------------------------------------------------------ L5: one board row per game
def test_L5_a_game_listed_twice_by_the_feed_gets_one_board_row():
    for books in ([[book("fanduel", 45.5, -110)], [book("pinnacle", 44.5, -108)]],
                  [[book("pinnacle", 44.5, -108)], [book("fanduel", 45.5, -110)]],
                  [[book("draftkings", 45.0, -110)], [book("pinnacle", 44.5, -108)]]):
        events = [event(books[0], "e1", "2026-10-10T19:00:00Z"), event(books[1], "e2", "2026-10-10T23:00:00Z")]
        oa = fetch.parse_odds_api(events, NAMES, "s")
        oa["day"] = pd.to_datetime(oa.commence_utc, utc=True).dt.strftime("%Y-%m-%d")
        up = pd.DataFrame(dict(game_id=[1], home_team=["Wyoming"], away_team=["Air Force"], day=["2026-10-10"]))
        out = up.merge(board.one_row_per_game(oa).drop(columns="commence_utc"), on=["home_team", "away_team", "day"],
                       how="left")
        assert len(out) == 1 and (out.line_src[0], out.mkt_total[0]) == ("pinnacle", 44.5)
    rematch = [event([book("pinnacle", 44.5, -108)]),
               event([book("pinnacle", 41.5, -110)], "e2", "2026-11-21T19:00:00Z")]
    oa = fetch.parse_odds_api(rematch, NAMES, "s")
    oa["day"] = pd.to_datetime(oa.commence_utc, utc=True).dt.strftime("%Y-%m-%d")
    assert len(board.one_row_per_game(oa)) == 2                    # a game on another day is another game


# ------------------------------------------------------------------ P5, P6, P8
def test_P5_P6_the_shared_price_helpers():
    one = pd.DataFrame(dict(price=[-110.0]))
    assert len(one[valid_odds(one.price)]) == 1 and valid_odds(-110) is True and valid_odds(np.inf) is False
    win, push = p_under_at(np.nan, 55.5, RESID)
    assert np.isnan(win) and np.isnan(push)


def test_P8_the_forecast_replay_is_priced_with_the_registered_model():
    """The committed replay's ev_under came from the pricing model before amendment 3 (1,709 rows off by
    0.0005 to 0.0028; no signal changed). Rerun with scripts/forecast_replay.py --no-fetch."""
    d = pd.read_parquet(ROOT / "data" / "processed" / "forecast_replay.parquet")
    assert np.array_equal(ev_under(d.close_total, d.entry_odds, d.close_total, RESID), d.ev_under.to_numpy())
