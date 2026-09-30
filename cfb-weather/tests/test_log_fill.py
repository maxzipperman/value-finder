"""Issue #76: scripts/log_fill.py records the largest stake a book would take (max_stake) and a note, as the
last two columns of fills.csv. The columns are optional, an older file is widened in place without touching
an old cell, and the scorer's cost-of-waiting report reads a file with the columns and one without alike."""
import csv
import importlib.util
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "log_fill.py"
OLD = "fill_utc,game_id,rule,line,price,book"
NEW = OLD + ",max_stake,note"


def load():
    spec = importlib.util.spec_from_file_location("log_fill_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def log(path, *extra, game="G1", rule="rule_b", at="2026-10-11T15:05Z"):
    return subprocess.run([sys.executable, str(SCRIPT), game, "--rule", rule, "--line", "44.5", "--price", "-108",
                           "--book", "fanduel", "--at", at, "--fills", str(path), *extra],
                          capture_output=True, text=True)


def read_text(path):
    return Path(path).read_bytes().decode("utf-8")


def test_a_new_file_has_the_two_columns_last_and_a_row_without_them_leaves_them_blank(tmp_path):
    p = tmp_path / "fills.csv"
    assert log(p).returncode == 0
    assert read_text(p) == NEW + "\n2026-10-11T15:05:00Z,G1,rule_b,44.5,-108.0,fanduel,,\n"


def test_a_row_with_a_size_and_a_note(tmp_path):
    p = tmp_path / "fills.csv"
    r = log(p, "--max-stake", "100", "--note", "slip said $100 max, \"limit\" shown")
    assert r.returncode == 0 and "up to $100" in r.stdout
    rows = list(csv.reader(read_text(p).splitlines()))
    assert rows[0] == NEW.split(",")
    assert rows[1][-2:] == ["100", 'slip said $100 max, "limit" shown']
    assert log(p, "--max-stake", "37.5", game="G2").returncode == 0
    assert list(csv.reader(read_text(p).splitlines()))[2][-2:] == ["37.5", ""]


@pytest.mark.parametrize("bad", ["0", "-5", "nan", "inf"])
def test_a_size_that_is_not_a_positive_number_is_refused_and_nothing_is_written(tmp_path, bad):
    p = tmp_path / "fills.csv"
    assert log(p, "--max-stake", bad).returncode != 0
    assert not p.exists()


def test_the_help_text_says_what_the_column_is_for(tmp_path):
    out = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True).stdout
    assert "--max-stake" in out and "$25 to $50" in out and "at least" in out


# Old files exactly as a Mac might hold them: odd number formats, a quoted cell with a comma, a blank line,
# a book with a stray space, CRLF endings, no final line end.
OLD_FILES = {
    "plain": OLD + "\n2026-10-02T15:05:00Z,2026_05_BUF_NE,rule_b,44.5,-108.0,fanduel\n",
    "odd": OLD + '\n2026-10-02T15:05:00Z,007,rule_b,44.50,-108,"fan, duel "\n\n2026-10-03T15:05:00Z,8,rule_b,+45,110.0,\n',
    "crlf": OLD + "\r\n2026-10-02T15:05:00Z,1,rule_b,44.5,-108.0,dk\r\n",
    "no_final_newline": OLD + "\n2026-10-02T15:05:00Z,1,rule_b,44.5,-108.0,dk",
    "header_only": OLD + "\n",
}


@pytest.mark.parametrize("name", OLD_FILES)
def test_an_old_file_is_widened_in_place_and_every_old_cell_is_kept_byte_for_byte(tmp_path, name):
    p = tmp_path / "fills.csv"
    old = OLD_FILES[name]
    p.write_bytes(old.encode())
    assert log(p, "--max-stake", "50", game="NEW").returncode == 0
    new = read_text(p)
    mod = load()
    old_records, new_records = mod.split_records(old), mod.split_records(new)
    assert len(new_records) == len(old_records) + 1
    added = new_records[-1]
    assert added.rstrip("\r\n").endswith(",50,")
    widened = new_records[:len(old_records)]
    for o, w in zip(old_records, widened):
        ob, oe = mod.body_and_end(o)
        wb, we = mod.body_and_end(w)
        if ob.strip() and ob != OLD:
            assert wb == ob + ",,"                    # the old cells untouched, two empty cells added
        elif ob == OLD:
            assert wb == NEW
        else:
            assert wb == ob                           # a blank line stays blank
        if oe:
            assert we == oe                           # the line ending is the one the file had
    assert new.startswith(NEW)


def test_appending_to_a_widened_file_leaves_earlier_rows_alone(tmp_path):
    p = tmp_path / "fills.csv"
    assert log(p, "--max-stake", "25").returncode == 0
    first = read_text(p)
    assert log(p, game="G2").returncode == 0
    assert read_text(p).startswith(first)
    assert log(p, "--note", "x", game="G3").returncode == 0
    assert read_text(p).startswith(first)


def test_a_file_with_a_header_we_do_not_know_is_left_alone(tmp_path):
    p = tmp_path / "fills.csv"
    p.write_text("when,game,price\n1,2,3\n")
    r = log(p)
    assert r.returncode != 0 and "unexpected header" in r.stderr
    assert p.read_text() == "when,game,price\n1,2,3\n"


def test_an_old_row_with_too_many_cells_stops_the_widening_and_nothing_changes(tmp_path):
    p = tmp_path / "fills.csv"
    p.write_text(OLD + "\n2026-10-02T15:05:00Z,1,rule_b,44.5,-108.0,dk,x,y,z\n")
    before = p.read_bytes()
    assert log(p).returncode != 0
    assert p.read_bytes() == before
    assert [f.name for f in tmp_path.iterdir()] == ["fills.csv"]        # no temp file left behind


# The scorer's cost-of-waiting report, on a fills file without the columns and the same fills with them.
def test_the_scorer_reports_the_same_with_and_without_the_new_columns(tmp_path):
    outs = []
    for name, text in (("old", OLD + "\n2026-10-09T12:00:00Z,{gid},rule_b,{line},-110.0,x\n"),
                       ("new", NEW + "\n2026-10-09T12:00:00Z,{gid},rule_b,{line},-110.0,x,,\n"),
                       ("new_filled", NEW + "\n2026-10-09T12:00:00Z,{gid},rule_b,{line},-110.0,x,40,\"a, b\"\n")):
        folder = tmp_path / name
        folder.mkdir()
        outs.append(score_with_fills(folder, text))
    assert "Cost of waiting, RULE_B: 1 paper fills" in outs[0]
    assert outs[0] == outs[1] == outs[2]


def score_with_fills(folder, text):
    kick = pd.Timestamp("2026-10-10T19:00:00Z")
    led = pd.DataFrame([dict(rules_version="cfb-v3-2026-09-28", game_id=1, kick_et="x", away_team="A", home_team="B",
                             venue="V", lead_days=2, wx_src="forecast", wx_wind=18, line_src="pinnacle", mkt_total=50.5,
                             mkt_under=-110, mkt_over=-110, ev_under=0.06, ht_threshold=62.6175, rule_b="SIGNAL",
                             rule_ht="below_threshold", start_utc=kick.strftime("%Y-%m-%dT%H:%M:%SZ"),
                             snapshot_utc=(kick - pd.Timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"))])
    sched = pd.DataFrame([dict(game_id=1, home_points=20, away_points=20, completed=True,
                               start_date=kick.strftime("%Y-%m-%dT%H:%M:%S.000Z"))])
    led.to_csv(folder / "ledger.csv", index=False)
    sched.to_csv(folder / "sched.csv", index=False)
    (folder / "fills.csv").write_text(text.format(gid=1, line=51.0))
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "score_forward.py"), "--ledger",
                           str(folder / "ledger.csv"), "--schedule", str(folder / "sched.csv"), "--now",
                           "2026-10-12"], capture_output=True, text=True, check=True).stdout
