"""The follow-up review of pull request 50 (the audit fixes) found smaller problems in the live alert path,
the run records and the price helpers. One test per finding, named by its id in the review (L1-L8, P4-P9):
the trigger poller on the widened ledger, the secondary LINE LAG label, games priced at the rule book in
the run record, the saved wind and total, one board row per game, a failed run's printout, the alert
state saved after each send and a damaged state file, prices that aren't prices, and key scrubbing."""
import json
import os
import runpy
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nflweather import board, config, live, notify, oddsapi, runlog  # noqa: E402
from nflweather.market import american_to_profit, ev_under, p_under_at, pricing_cohort, valid_odds  # noqa: E402

RESID = pricing_cohort(board.PRICING_COHORT_SHA256)
KEY = "0123456789abcdef0123456789abcdef"            # a made-up key, 32 hex characters like the real one


# ------------------------------------------------------------------ L1: the trigger poller on the widened ledger
WIDE = ("snapshot_utc,rules_version,game_id,gameday,gametime,away_team,home_team,lead_days,wx_src,wx_wind,wx_temp,"
        "wx_precip,wx_snow,line_src,total_line,under_odds,over_odds,p_under,p_market,lean,ev_under,rule_b,best_under,"
        "best_under_book,ref_total,best_line,best_line_under,best_line_book,ev_best_line,quote_utc,quote_update,wx_hash,"
        "wx_fetched_utc,wx_wind_dir,wx_cross,wx_along").split(",")        # the ledger's columns since amendment 5


def test_L1_the_trigger_poller_reads_the_widened_ledger(tmp_path):
    row = dict.fromkeys(WIDE, "") | dict(snapshot_utc="2026-10-09T11:30:00Z", rules_version=board.RULES_VERSION,
                                         game_id="g1", gameday="2026-10-11", gametime="13:00", away_team="CHI",
                                         home_team="GB", lead_days=2, wx_wind=16.2, rule_b="negative_ev",
                                         quote_utc="2026-10-09T11:29:58Z", quote_update="2026-10-09T11:20:00Z")
    pd.DataFrame([row], columns=WIDE).to_csv(tmp_path / "ledger.csv", index=False)
    ledger = pd.read_csv(tmp_path / "ledger.csv")                  # as scripts/poll_triggers.py reads it
    feed = pd.DataFrame([dict(snapshot_utc="2026-10-09T1600Z", event_id="e1", commence_utc="2026-10-11T17:00:00Z",
                              home="GB", away="CHI", book=b, market="totals", book_update="x", total=41.5,
                              under_price=u, over_price=-105) for b, u in (("pinnacle", -112), ("draftkings", -110))])
    r = live.trigger_rows(live.active_triggers(ledger, pd.Timestamp("2026-10-09T16:00:00Z")), feed, "p")
    assert list(r.book) == ["pinnacle", "draftkings"] and list(r.under_price) == [-112, -110]
    assert set(r.ledger_snapshot_utc) == {"2026-10-09T11:30:00Z"} and set(r.quote_utc) == {"2026-10-09T1600Z"}
    assert r.iloc[0].kick_utc == "2026-10-11T17:00:00Z" and r.iloc[0].wx_wind == 16.2


# ------------------------------------------------------------------ the alert run, offline
BOARD = dict(game_id="2026_06_NE_BUF", away_team="NE", home_team="BUF", gameday="2030-10-13", gametime="13:00",
             conditions="18 mph, 50°F", lead_days=2, wx_src="era5", wx_wind=18.0, wx_temp=50.0, wx_precip=0.0,
             wx_snow=0.0, line_src="pinnacle", mkt_total=44.5, mkt_under=-108.0, ev_under=0.09, rule_b="SIGNAL",
             best_under=np.nan, best_under_book="", best_line=np.nan, best_line_under=np.nan, best_line_book="",
             ev_best_line=np.nan, lean="", p_under=0.5, p_market=0.5, edge=0.0, v_dome=0, v_city_temp7=50.0,
             spread_line=3.0)
OTHER = dict(BOARD, game_id="2026_06_MIA_NYJ", home_team="NYJ", away_team="MIA")


def run_alerts(tmp_path, monkeypatch, rows, state=None, send=None, save=None, dry=False):
    """One run of scripts/alerts.py with everything under tmp_path: (sent, runs, exit status, saved state)."""
    sent, fwd = [], tmp_path / "data" / "forward"
    fwd.mkdir(parents=True, exist_ok=True)
    if state is not None:
        (fwd / "alert_state.json").write_text(state if isinstance(state, str) else json.dumps(state))
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(board, "compute", lambda **k: pd.DataFrame(rows))
    monkeypatch.setattr(board, "save", save or (lambda up: None))
    monkeypatch.setattr(oddsapi, "has_key", lambda: False)
    monkeypatch.setattr(notify, "send", send or (lambda title, body: sent.append((title, body)) or True))
    monkeypatch.setattr(sys, "argv", ["alerts.py"] + (["--dry-run"] if dry else []))
    code = 0
    try:
        runpy.run_path(str(ROOT / "scripts" / "alerts.py"), run_name="__main__")
    except SystemExit as e:
        code = e.code
    runs = fwd / "runs.csv"
    runs = pd.read_csv(runs, keep_default_na=False) if runs.exists() else None
    saved = json.loads((fwd / "alert_state.json").read_text()) if (fwd / "alert_state.json").exists() else None
    return sent, runs, code, saved


def test_L2_a_secondary_line_lag_says_secondary_price(tmp_path, monkeypatch):
    state = {BOARD["game_id"]: {"sent": ["ruleb_secondary"], "wind": 12.0, "total": 44.5}}
    row = dict(BOARD, line_src="nflverse", rule_b="SIGNAL_SECONDARY")
    sent, runs, code, _ = run_alerts(tmp_path, monkeypatch, [row], state=state)
    assert code == 0 and [t.split(":")[0] for t, _ in sent] == ["RULE B LINE LAG (secondary price) 44.5 at -108"]
    assert "not part of the registered test" in sent[0][1]
    state = {BOARD["game_id"]: {"sent": ["ruleb"], "wind": 12.0, "total": 44.5}}
    sent, _, _, _ = run_alerts(tmp_path, monkeypatch, [BOARD], state=state)          # Pinnacle's price: unchanged
    assert [t.split(":")[0] for t, _ in sent] == ["RULE B LINE LAG 44.5 at -108"]


def test_L3_the_run_record_counts_games_priced_at_pinnacle(tmp_path, monkeypatch):
    backup = dict(OTHER, line_src="nflverse", rule_b="SIGNAL_SECONDARY")
    _, runs, _, _ = run_alerts(tmp_path, monkeypatch, [BOARD, backup])
    assert runs.columns[-1] == "rule_priced" and runs[["priced", "rule_priced"]].values.tolist() == [[2, 1]]


def test_L3_an_old_runs_file_is_widened_once_and_its_old_rows_keep_every_character(tmp_path):
    path = tmp_path / "runs.csv"
    old = ("run_utc,job,rules_version,status,games,signals,priced,unmapped,error\r\n"
           "2026-09-29T14:30:05Z,nfl-alerts,v3-2026-09-28,ok,16,0,16,,\r\n"
           '2026-09-29T18:30:04Z,nfl-alerts,v3-2026-09-28,failed,16,1,14,"Foo, Bar","while x: E: a ""b"", c"\r\n')
    path.write_bytes(old.encode())
    runlog.record_run(path, "nfl-alerts", "v3-2026-09-28", "ok", games=16, priced=16, rule_priced=0)
    text = path.read_bytes().decode()
    lines = old.split("\r\n")[:-1]
    assert text.startswith(lines[0] + ",rule_priced\r\n" + "".join(ln + ",\r\n" for ln in lines[1:]))
    runs = pd.read_csv(path, keep_default_na=False)
    assert list(runs.columns) == runlog.RUN_COLS and len(runs) == 3
    assert runs.unmapped[1] == "Foo, Bar" and runs.error[1] == 'while x: E: a "b", c'
    assert runs.rule_priced.tolist() == ["", "", "0"]                  # old runs: blank, not zero
    assert not (tmp_path / "runs.csv.tmp").exists()
    before = path.read_bytes()
    runlog.record_run(path, "nfl-alerts", "v3-2026-09-28", "ok", rule_priced=12)      # later runs only append
    assert path.read_bytes().startswith(before) and pd.read_csv(path).rule_priced.tolist()[-1] == 12


def test_L3_a_hand_edited_runs_file_is_still_widened(tmp_path):
    path = tmp_path / "runs.csv"
    path.write_text('run_utc,job,rules_version,status,games,signals,priced,unmapped,error\n'
                    '2026-09-29T14:30:05Z,nfl-alerts,v3,failed,1,0,1,,"two\nlines"')          # no line end at the end
    runlog.record_run(path, "nfl-alerts", "v3", "ok", rule_priced=1)
    runs = pd.read_csv(path, keep_default_na=False)
    assert list(runs.columns) == runlog.RUN_COLS and runs.error[0] == "two\nlines"
    assert runs.rule_priced.tolist() == ["", "1"]
    path.write_text("run_utc,job,rules_version,status,games,signals,priced,unmapped,error\r\n"
                    "2026-09-29T14:30:05Z,nfl-alerts,v3,ok,1,0,1,,")                  # cut off before its line end
    runlog.record_run(path, "nfl-alerts", "v3", "ok", rule_priced=1)
    assert path.read_text().splitlines()[1] == "2026-09-29T14:30:05Z,nfl-alerts,v3,ok,1,0,1,,,"
    assert pd.read_csv(path).rule_priced.tolist()[-1] == 1


def test_L4_a_game_whose_alerts_fail_keeps_its_last_wind_and_total(tmp_path, monkeypatch):
    state = {OTHER["game_id"]: {"sent": [], "wind": 10.0, "total": 44.5}}
    bad = dict(OTHER, wx_precip="not a number")                       # its alert text raises
    sent, runs, code, saved = run_alerts(tmp_path, monkeypatch, [bad, BOARD], state=state)
    assert code == 1 and runs.status.tolist() == ["failed"]
    assert (saved[OTHER["game_id"]]["wind"], saved[OTHER["game_id"]]["total"]) == (10.0, 44.5)
    assert saved[BOARD["game_id"]]["wind"] == 18.0                    # the other game's are saved as usual
    sent, _, code, _ = run_alerts(tmp_path, monkeypatch, [OTHER])      # fixed next run: its LINE LAG still comes
    assert code == 0 and any(t.startswith("RULE B LINE LAG 44.5 at -108: MIA @ NYJ") for t, _ in sent)


def test_L6_a_failed_run_prints_the_error_without_the_key_and_exits_1(tmp_path, monkeypatch, capsys):
    def down(**k):
        raise ConnectionError(f"GET https://api.the-odds-api.com/v4/odds?regions=us&apiKey={KEY} failed")
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(board, "compute", down)
    monkeypatch.setattr(oddsapi, "has_key", lambda: False)
    monkeypatch.setattr(notify, "send", lambda title, body: True)
    monkeypatch.setattr(sys, "argv", ["alerts.py"])
    with pytest.raises(SystemExit) as e:
        runpy.run_path(str(ROOT / "scripts" / "alerts.py"), run_name="__main__")
    out = capsys.readouterr()
    assert e.value.code == 1 and KEY not in out.out + out.err
    assert "run failed while building the board: ConnectionError" in out.out and "apiKey=***" in out.out
    assert "Traceback" not in out.out + out.err


def test_L7_a_send_that_fails_part_way_is_not_repeated_next_run(tmp_path, monkeypatch):
    calls = []

    def flaky(title, body):
        calls.append(title)
        if len(calls) == 2:
            raise ConnectionError("ntfy unreachable")
        return True
    _, runs, code, saved = run_alerts(tmp_path, monkeypatch, [BOARD, OTHER], send=flaky)
    assert code == 1 and runs.error[0].startswith("while sending the alerts: ConnectionError")
    assert saved[BOARD["game_id"]]["sent"] == ["ruleb"] and saved[OTHER["game_id"]].get("sent", []) == []
    assert "wind" not in saved[OTHER["game_id"]]      # its alert never went out: its wind waits for the next run
    sent, runs, code, _ = run_alerts(tmp_path, monkeypatch, [BOARD, OTHER])
    assert code == 0 and [t for t, _ in sent] == [calls[1]]     # only the one that didn't go out


def test_L7_a_state_file_that_cannot_be_written_does_not_stop_the_alerts(tmp_path, monkeypatch):
    def full(path, state):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(runlog, "write_alert_state", full)
    sent, runs, code, _ = run_alerts(tmp_path, monkeypatch, [BOARD, OTHER])
    assert [t.split(":")[1].strip() for t, _ in sent[:2]] == ["NE @ BUF 10-13 13", "MIA @ NYJ 10-13 13"]  # both sent
    assert code == 1 and runs.error[0].startswith("while saving the alert state: RuntimeError: alert_state.json "
                                                  "could not be saved (OSError: [Errno 28] No space left on device)")


def test_L8_a_damaged_state_file_costs_no_ledger_row(tmp_path, monkeypatch):
    saved_boards = []
    sent, runs, code, saved = run_alerts(tmp_path, monkeypatch, [BOARD], state='{"2026_06_NE_BUF": {"sent": [',
                                         save=saved_boards.append)
    fwd = tmp_path / "data" / "forward"
    assert code == 0 and len(saved_boards) == 1 and len(sent) == 2     # the ledger saved, the alert and a notice sent
    assert runs.status.tolist() == ["ok"] and runs.error[0].startswith("alert_state.json could not be read")
    (copy,) = fwd.glob("alert_state.corrupt-*.json")
    assert copy.read_text() == '{"2026_06_NE_BUF": {"sent": [' and copy.name in runs.error[0]
    assert saved[BOARD["game_id"]]["sent"] == ["ruleb"] and not list(fwd.glob("*.tmp"))


def test_L8_a_dry_run_leaves_a_damaged_state_file_alone(tmp_path, monkeypatch):
    sent, runs, code, _ = run_alerts(tmp_path, monkeypatch, [BOARD], state="[]", dry=True)
    fwd = tmp_path / "data" / "forward"
    assert code == 0 and runs is None and (fwd / "alert_state.json").read_text() == "[]" and sent == []
    assert not list(fwd.glob("alert_state.corrupt-*"))


DAMAGED = "NFL weather alerts: the alert record was damaged"


def test_a_damaged_state_file_tells_the_owner_once(tmp_path, monkeypatch):
    """The run keeps a copy, starts from an empty state and is recorded ok, and one notice says so."""
    sent, runs, code, _ = run_alerts(tmp_path, monkeypatch, [BOARD], state='{"2026_06_NE_BUF": {"sent": [')
    (copy,) = (tmp_path / "data" / "forward").glob("alert_state.corrupt-*.json")
    notices = [body for title, body in sent if title == DAMAGED]
    assert code == 0 and runs.status.tolist() == ["ok"] and len(notices) == 1
    assert copy.name in notices[0] and "ledger row was saved" in notices[0] and "once more" in notices[0]
    assert [t for t, _ in sent if t != DAMAGED] == ["RULE B WIND UNDER 44.5 at -108: NE @ BUF 10-13 13:00 ET"]
    sent, runs, code, _ = run_alerts(tmp_path, monkeypatch, [BOARD])       # the next run reads the new state
    assert code == 0 and sent == []


def test_a_damaged_state_notice_that_cannot_be_sent_does_not_stop_the_run(tmp_path, monkeypatch):
    got = []

    def send(title, body):
        if title == DAMAGED:
            raise ConnectionError("ntfy unreachable")
        return got.append(title) or True
    _, runs, code, saved = run_alerts(tmp_path, monkeypatch, [BOARD], state="[]", send=send)
    assert code == 0 and runs.status.tolist() == ["ok"] and len(got) == 1 and saved[BOARD["game_id"]]["sent"] == ["ruleb"]


# ------------------------------------------------------------------ a stored wind or total that isn't a number
@pytest.mark.parametrize("wind,total", [("12", 44.5), (12.0, "44.5"), ([12.0], 44.5), (True, 44.5), (12.0, {"t": 1})])
def test_a_stored_wind_or_total_that_is_not_a_number_counts_as_missing(tmp_path, monkeypatch, wind, total):
    """A hand edit used to fail that game's alerts on every run until kickoff."""
    state = {BOARD["game_id"]: {"sent": ["ruleb"], "wind": wind, "total": total}}
    sent, runs, code, saved = run_alerts(tmp_path, monkeypatch, [BOARD], state=state)
    assert code == 0 and runs.status.tolist() == ["ok"] and sent == []          # no earlier check: no LINE LAG
    assert (saved[BOARD["game_id"]]["wind"], saved[BOARD["game_id"]]["total"]) == (18.0, 44.5)
    state = {BOARD["game_id"]: {"sent": ["ruleb"], "wind": 12, "total": 44.5}}  # a whole number is still a number
    sent, _, code, _ = run_alerts(tmp_path, monkeypatch, [BOARD], state=state)
    assert code == 0 and [t.split(":")[0] for t, _ in sent] == ["RULE B LINE LAG 44.5 at -108"]


# ------------------------------------------------------------------ widening runs.csv keeps its permissions
@pytest.mark.parametrize("mode", [0o600, 0o664])
def test_widening_the_run_record_keeps_its_permissions(tmp_path, mode):
    path = tmp_path / "runs.csv"
    path.write_text("run_utc,job,rules_version,status,games,signals,priced,unmapped,error\n"
                    "2026-09-29T14:30:05Z,nfl-alerts,v3,ok,1,0,1,,\n")
    path.chmod(mode)
    runlog.record_run(path, "nfl-alerts", "v3", "ok", rule_priced=1)
    assert pd.read_csv(path).columns[-1] == "rule_priced" and stat.S_IMODE(path.stat().st_mode) == mode


# ------------------------------------------------------------------ the nightly ledger sync
def sync_ledgers(tmp_path, files):
    """Run ops/sync_ledgers.sh on a throwaway repo whose origin is a local bare repo, with HOME (and so the
    script's clone) inside tmp_path; nothing outside tmp_path is read or written. Returns the exit status
    and the files on the `ledgers` branch of the bare repo."""
    repo, remote = tmp_path / "repo", tmp_path / "remote.git"
    env = dict(os.environ, HOME=str(tmp_path / "home"), GIT_CEILING_DIRECTORIES=str(tmp_path), GIT_CONFIG_NOSYSTEM="1",
               GIT_CONFIG_GLOBAL=os.devnull, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    git = lambda *a: subprocess.run(["git", *a], check=True, capture_output=True, text=True, env=env).stdout
    if not remote.exists():
        git("init", "-q", "--bare", str(remote))
        (repo / "ops").mkdir(parents=True)
        shutil.copy(ROOT.parent / "ops" / "sync_ledgers.sh", repo / "ops")
        git("init", "-q", str(repo))
        git("-C", str(repo), "remote", "add", "origin", str(remote))
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    code = subprocess.run(["bash", str(repo / "ops" / "sync_ledgers.sh")], capture_output=True, env=env).returncode
    return code, git("--git-dir", str(remote), "ls-tree", "-r", "--name-only", "ledgers").split()


def test_the_nightly_sync_publishes_decisions_csv(tmp_path):
    ledgers = {f"{p}/data/forward/ledger.csv": "snapshot_utc\n2026-09-29T14:30:05Z\n" for p in ("nfl-weather", "cfb-weather")}
    code, files = sync_ledgers(tmp_path, ledgers)
    assert code == 0 and files == ["cfb-weather/ledger.csv", "nfl-weather/ledger.csv"]     # no decisions.csv: as before
    code, files = sync_ledgers(tmp_path, {"nfl-weather/data/forward/decisions.csv": "game_id,decision\ng1,bet\n"})
    assert code == 0 and files == ["cfb-weather/ledger.csv", "nfl-weather/decisions.csv", "nfl-weather/ledger.csv"]


# ------------------------------------------------------------------ the owner's page (ops/RUN_RECORDS.md)
def test_the_owners_page_says_what_the_jobs_do():
    page = " ".join((ROOT.parent / "ops" / "RUN_RECORDS.md").read_text().split())
    assert "none is sent twice" not in page and "can show twice" in page                     # a failed send's banner
    assert "the forecasts or the odds" not in page and "An odds outage does not fail a run" in page
    assert "no ledger row, no run record and no alert state" in page and "backup" in page    # a dry run
    assert "the alert record was damaged" in page


def test_L8_the_state_file_is_replaced_in_one_step(tmp_path, monkeypatch):
    path = tmp_path / "alert_state.json"
    runlog.write_alert_state(path, {"g": {"sent": ["ruleb"]}})
    real = Path.write_text

    def half(self, text, *a, **k):          # the disk fills half way through writing the new state
        real(self, text[: len(text) // 2], *a, **k)
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(Path, "write_text", half)
    with pytest.raises(OSError):
        runlog.write_alert_state(path, {"g": {"sent": ["ruleb", "lag20"]}})
    monkeypatch.undo()
    assert json.loads(path.read_text()) == {"g": {"sent": ["ruleb"]}}


# ------------------------------------------------------------------ L5: one board row per game
def feed(event, book, total, under, home="BUF", away="NE"):
    return dict(snapshot_utc="2026-10-09T1430Z", event_id=event, commence_utc="2026-10-11T17:00:00Z", home=home,
                away=away, home_name=home, away_name=away, book=book, market="totals", total=total, over_price=-110,
                under_price=under, book_update="2026-10-09T14:28:00Z")


@pytest.mark.parametrize("order", [1, -1])
def test_L5_a_game_listed_twice_by_the_feed_gets_one_board_row(monkeypatch, order):
    rows = [feed("e1", "fanduel", 45.5, -110), feed("e2", "pinnacle", 44.5, -108), feed("e2", "draftkings", 45.0, -112),
            feed("e3", "pinnacle", 38.5, -105, "MIN", "MIA")][::order]
    monkeypatch.setattr(oddsapi, "live", lambda **k: pd.DataFrame(rows))
    pin = board._pinnacle_live()
    assert len(pin) == 2 and pin.set_index("home_team").loc["BUF", "pin_total"] == 44.5
    up = pd.DataFrame(dict(home_team=["BUF", "MIN"], away_team=["NE", "MIA"], gameday="2026-10-11",
                           total_line=[44.0, 38.0], under_odds=-110.0, over_odds=-110.0))
    out = board.use_pinnacle(up, pin)
    assert len(out) == 2 and out.line_src.tolist() == ["pinnacle", "pinnacle"]


# ------------------------------------------------------------------ P4-P6: prices that aren't prices
def test_P4_a_number_that_is_not_a_price_is_never_the_best():
    t = pd.DataFrame(dict(event_id="e", book=["pinnacle", "a", "b", "c"], total=[44.0, 47.5, 44.0, 45.0],
                          under_price=[-110, 50, 60, -112]))
    b = board.best_line(t).iloc[0]
    assert (b.best_line, b.best_line_under, b.best_line_book) == (45.0, -112, "c")      # not 47.5 at +50
    u = board.best_under(t).iloc[0]
    assert (u.best_under, u.best_under_book) == (-110, "pinnacle")                       # not +60 at 44
    no_quote = t.assign(under_price=[0, -105, -104, -110])                              # Pinnacle's 0 isn't a price
    assert board.best_under(no_quote).empty


def test_P5_a_missing_line_or_reference_is_not_a_certain_win():
    for line, ref in ((np.nan, 44.5), (44.5, None), (pd.NA, 44.5), (44.5, np.inf)):
        win, push = p_under_at(line, ref, RESID)
        assert np.isnan(win) and np.isnan(push)
    win, _ = p_under_at(np.array([44.5, np.nan]), np.array([44.5, 44.5]), RESID)
    assert 0 < win[0] < 1 and np.isnan(win[1])
    assert not valid_odds(np.inf) and not valid_odds(-np.inf)
    assert np.isnan(american_to_profit(np.inf)).all() and np.isnan(ev_under(44.5, np.inf, 44.5, RESID)).all()


def test_P6_valid_odds_gives_one_answer_per_element_for_a_list():
    one = pd.DataFrame(dict(price=[-110.0]))
    assert len(one[valid_odds(one.price)]) == 1                       # a one-row frame can be filtered
    assert valid_odds(pd.Series([50])).tolist() == [False] and valid_odds([-110, 50]).tolist() == [True, False]
    for scalar in (-110, -110.0, np.float64(-110), np.int64(105), "-110"):
        assert valid_odds(scalar) is True
    for scalar in (50, None, np.nan, pd.NA, "x"):
        assert valid_odds(scalar) is False
    assert pd.Series([-110.0, 50.0, np.nan]).map(valid_odds).tolist() == [True, False, False]   # use_pinnacle's way


# ------------------------------------------------------------------ P9: keys in error text
LEAKS = [f"url: /odds?apiKey%3D{KEY}%26markets%3Dtotals", f"https%3A%2F%2Fapi.the-odds-api.com%2Fv4%3FapiKey%3D{KEY}",
         f'{{"apiKey": "{KEY}", "markets": "totals"}}', f"{{'apiKey': '{KEY}', 'bookmakers': 'pinnacle'}}",
         f"apiKey: {KEY}", f"apiKey = {KEY}", f"headers {{'x-api-key': '{KEY}'}}", f"x-api-key: {KEY}",
         f"ODDS_API_KEY={KEY}", f"access_token={KEY}", f"my_api_key={KEY}", f"Authorization: Bearer {KEY}",
         f"Bearer {KEY}", f"Authorization: Basic {KEY}", f"oddsApiKey={KEY}", f"accessToken: {KEY}",
         f"params={{'regions': 'us', 'apiKey': '{KEY}'}}", f"key=<{KEY}>", f"?apiKey={KEY}#frag",
         f"the_very_long_environment_variable_name_prefix_that_goes_on_api_key={KEY}",
         f"HTTPSConnectionPool(host='api.the-odds-api.com', port=443): Max retries exceeded with url: "
         f"/v4/sports/americanfootball_nfl/odds?regions=us&apiKey={KEY}&markets=totals (Caused by X)"]


@pytest.mark.parametrize("text", LEAKS)
def test_P9_every_way_a_key_can_appear_is_blanked(text):
    out = runlog.scrub(text)
    assert KEY not in out and "***" in out


@pytest.mark.parametrize("text,want", [(f"key={KEY};other", "key=***;other"), (f"key={KEY},other", "key=***,other"),
                                       (f"key={KEY}]", "key=***]"), (f"token={KEY}}}", "token=***}"),
                                       (f"apiKey={KEY}&regions=us", "apiKey=***&regions=us"),
                                       (f"apiKey%3D{KEY}%26x%3D1", "apiKey%3D***%26x%3D1")])
def test_P9_the_text_after_a_key_survives(text, want):
    assert runlog.scrub(text) == want


ORDINARY = [
    "KeyError: 'mkt_under'",
    "KeyError: \"None of [Index(['pin_total'], dtype='object')] are in the [columns]\"",
    "TypeError: sort_values() got an unexpected keyword argument 'keys'",
    "while building the board: ConnectionError: HTTPSConnectionPool(host='api.open-meteo.com', port=443): "
    "Read timed out. (read timeout=60)",
    "HTTPError: 502 Server Error: Bad Gateway for url: https://api.open-meteo.com/v1/forecast?latitude=42.774"
    "&longitude=-78.787&hourly=wind_speed_10m",
    "OddsAPIUnavailable: The Odds API rejected the key, or the plan is out of credits (401)",
    "OSError: [Errno 28] No space left on device: '/Users/x/data/forward/ledger.csv.tmp'",
    "ValueError: pricing_cohort.json is not the registered cohort: its residuals hash to 897a61b6846b077b, "
    "PREREGISTRATION.md registers c49a6649c3f86ac1",
    "JSONDecodeError: Expecting value: line 1 column 1 (char 0)",
    "ParserError: Error tokenizing data. C error: Expected 9 fields in line 3, saw 10",
    "RuntimeError: 1 game(s) raised: MIA @ NYJ 10-13 13:00 ET: TypeError: '>=' not supported between "
    "instances of 'str' and 'float'",
    "monkey=banana turkey=club; hockey: 3, the secretary's keyboard, a token of thanks, keys: none",
    "no ODDS_API_KEY",
]


@pytest.mark.parametrize("text", ORDINARY)
def test_P9_ordinary_error_text_is_left_alone(text):
    assert runlog.scrub(text) == text


def test_P9_a_very_long_message_is_scrubbed_quickly():
    """A failed run scrubs its error before anything else, so scrubbing must never stall on odd text."""
    start = time.perf_counter()
    for text in ("a-" * 100_000, "aB" * 100_000, "%3Fa" * 50_000, "key_" * 50_000):
        runlog.scrub(text)
    assert time.perf_counter() - start < 5
