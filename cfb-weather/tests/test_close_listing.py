"""Amendment 6 (draft, Sep 30): Astra's audit 3, blockers 1 and 2 (issue 88). A captured close is used only for the
listing it was captured for, 2 to 20 minutes before that listing's kickoff, and the test's end is judged on the
schedule's kickoff as well as the entry row's. The audit's two cases fail on the scorer as it was on main on Sep 29
(commit 30444ec) and pass here. Every input is synthetic, or the committed 2025 rehearsal; no 2026 price or result is
read, and every run is a preview (--now) on a test ledger (--ledger)."""
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REFUSED = "close captured outside the window for this listing (2 to 20 minutes before its kickoff)"


def ts(x):
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def z(x):
    return ts(x).strftime("%Y-%m-%dT%H:%M:%SZ")


def row(gid, kick, snap, **kw):
    base = dict(rules_version="cfb-v3-2026-09-28", game_id=gid, kick_et="x", away_team="A", home_team="B", venue="V",
                lead_days=2, wx_src="forecast", wx_wind=18, line_src="pinnacle", mkt_total=50.5, mkt_under=-110,
                mkt_over=-110, ev_under=0.06, ht_threshold=62.6175, rule_b="no_trigger", rule_ht="below_threshold",
                start_utc=z(kick), snapshot_utc=z(snap))
    return base | kw


def sched(gid, hp=20, ap=20, kick=None):
    s = dict(game_id=gid, home_points=hp, away_points=ap, completed=True)
    return s | ({"start_date": ts(kick).strftime("%Y-%m-%dT%H:%M:%S.000Z")} if kick else {})


def cap(gid, captured, kick, total, src="pinnacle"):
    """A row of closes.csv as scripts/capture_close.py writes it: captured at `captured` for the kickoff `kick`."""
    return dict(capture_utc=z(captured), game_id=gid, start_utc=z(kick), home_team="B", away_team="A", line_src=src,
                close_total=total, close_under=-110, close_over=-110)


def score(folder, rows, schedule, now, *extra, closes=None):
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(folder / "ledger.csv", index=False)
    pd.DataFrame(schedule).to_csv(folder / "sched.csv", index=False)
    if closes is not None:
        pd.DataFrame(closes).to_csv(folder / "closes.csv", index=False)
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "score_forward.py"), "--ledger",
                           str(folder / "ledger.csv"), "--schedule", str(folder / "sched.csv"), "--now", now, *extra],
                          capture_output=True, text=True, check=True).stdout


def rb(out):
    return out.split("RULE_B:")[1].split("RULE_HT:")[0]


def ht(out):
    return out.split("RULE_HT:")[1].split("Variants under")[0]


def signal(gid, kick, entry=50.5):
    """A Rule B signal logged 2 days out, with no later quote: its primary close can only be the captured close."""
    return row(gid, kick, ts(kick) - pd.Timedelta(days=2), rule_b="SIGNAL", mkt_total=entry)


# ------------------------------------------------------------------ blocker 1: the audit's case
def test_blocker_1_a_new_listing_never_inherits_the_close_captured_for_an_earlier_one(tmp_path):
    """Game 999, listed Oct 10 19:00, its only captured close (40) taken Oct 10 at 18:50; postponed to Oct 31 and
    signalled again at 60. Main graded the Oct 31 listing against the Oct 10 close: mean CLV +20.00."""
    rows = [signal(999, "2026-10-10T19:00Z"), signal(999, "2026-10-31T19:00Z", entry=60.0)]
    closes = [cap(999, "2026-10-10T18:50Z", "2026-10-10T19:00Z", 40.0)]
    out = score(tmp_path, rows, [sched(999, kick="2026-10-31T19:00Z")], "2026-11-15", closes=closes)
    r = rb(out)
    assert "2 signals, 1 settled, 0 pending, 1 void (not graded)" in r
    assert "mean CLV +20.00" not in r and "0 of 1 bets have a primary close" in r
    assert "primary close: 0 from a later logged quote, 0 from the captured close, 1 with none" in r
    assert "secondary (amendment 2): no captured closes for these 1 bets" in r
    assert f"captured close refused for 1 of these 1 bets: {REFUSED}; counted as missing (999)" in r
    assert "close from: {'none': 1}" in r
    # --list-excluded prints the capture refused: when it was taken, for which kickoff, and the listing's kickoff
    listed = rb(score(tmp_path, rows, [sched(999, kick="2026-10-31T19:00Z")], "2026-11-15", "--list-excluded",
                      closes=closes))
    line = next(ln for ln in listed.splitlines() if ln.strip().startswith("999 ") and REFUSED in ln)
    assert "2026-10-10T18:50:00Z" in line and "2026-10-10T19:00:00Z" in line and "2026-10-31 19:00:00+00:00" in line


# ------------------------------------------------------------------ blocker 2: the audit's case
def test_blocker_2_a_game_moved_past_the_test_end_never_counts(tmp_path):
    """Rule HT game 901: entry row kickoff Jan 31, 2028 23:00 UTC, final schedule kickoff Feb 1, 2028 20:00 UTC (21
    hours later, so not void). Main settled it and printed it in a FINAL decision: STAY ON PAPER, 1-0-0."""
    rows = [row(901, "2028-01-31T23:00Z", "2028-01-31T19:00Z", rule_ht="SIGNAL", mkt_total=65.5)]
    out = score(tmp_path, rows, [sched(901, kick="2028-02-01T20:00Z")], "2028-02-02")
    assert "ledger rows: 1; in the test: 0" in out and "excluded, after the 2027 season: 1" in out
    assert "RULE_HT: 0 signals at the last quote before kickoff, 0 settled, 0 pending, 0 void" in out
    assert "FINAL" not in out and "record 1-0-0" not in out
    listed = score(tmp_path, rows, [sched(901, kick="2028-02-01T20:00Z")], "2028-02-02", "--list-excluded")
    assert re.search(r"901 .*after the 2027 season", listed)


def test_blocker_2_the_row_s_own_kickoff_still_counts_and_decides_without_a_schedule_kickoff(tmp_path):
    """A row dated from Feb 1, 2028 is excluded whatever the schedule says (as before), and a game the schedule gives
    no kickoff for is judged on its row alone (the declared behaviour, kept)."""
    moved_back = [row(902, "2028-02-01T01:00Z", "2028-01-31T19:00Z", rule_ht="SIGNAL", mkt_total=65.5)]
    out = score(tmp_path / "a", moved_back, [sched(902, kick="2028-01-31T20:00Z")], "2028-02-02")
    assert "in the test: 0" in out and "excluded, after the 2027 season: 1" in out
    game = [row(903, "2028-01-31T23:00Z", "2028-01-31T19:00Z", rule_ht="SIGNAL", mkt_total=65.5)]
    out = score(tmp_path / "b", game, [sched(903)], "2028-02-02")                     # no kickoff column at all
    assert "the check for moved games is off" in out and "in the test: 1" in out
    assert "RULE_HT: 1 signals at the last quote before kickoff, 1 settled" in out
    both = [sched(903), sched(904, kick="2028-01-30T20:00Z")]                          # a kickoff for another game only
    out = score(tmp_path / "c", game, both, "2028-02-02")
    assert "in the test: 1" in out and "1 settled" in ht(out)


def test_blocker_2_a_game_inside_the_test_on_both_kickoffs_still_counts(tmp_path):
    rows = [row(905, "2028-01-31T20:00Z", "2028-01-31T16:00Z", rule_ht="SIGNAL", mkt_total=65.5)]
    out = score(tmp_path, rows, [sched(905, kick="2028-01-31T23:59Z")], "2028-02-02")
    assert "in the test: 1" in out and "FINAL: STAY ON PAPER" in out


# ------------------------------------------------------------------ the window
def test_a_close_captured_inside_the_window_is_used_at_both_ends(tmp_path):
    """10 minutes before kickoff, and exactly 2 and exactly 20: all three are the listing's close."""
    kicks = ["2026-10-10T19:00Z", "2026-10-17T19:00Z", "2026-10-24T19:00Z"]
    rows = [signal(1 + i, k) for i, k in enumerate(kicks)]
    closes = [cap(1 + i, ts(k) - pd.Timedelta(minutes=m), k, 50.5 - d)
              for i, (k, m, d) in enumerate(zip(kicks, (10, 2, 20), (1.0, 2.0, 3.0)))]
    r = rb(score(tmp_path, rows, [sched(1 + i, kick=k) for i, k in enumerate(kicks)], "2026-11-01", closes=closes))
    assert "primary close: 0 from a later logged quote, 3 from the captured close, 0 with none" in r
    assert "mean CLV +2.00" in r and "3 of 3 bets have a primary close" in r
    assert "0 of 3 bets without a captured close" in r and "refused" not in r


def test_a_close_captured_21_minutes_or_1_minute_before_kickoff_or_after_it_is_not_used(tmp_path):
    kicks = ["2026-10-10T19:00Z", "2026-10-17T19:00Z", "2026-10-24T19:00Z", "2026-10-31T19:00Z"]
    rows = [signal(1 + i, k) for i, k in enumerate(kicks)]
    closes = [cap(1 + i, ts(k) - pd.Timedelta(minutes=m), k, 49.5) for i, (k, m) in enumerate(zip(kicks,
                                                                                             (21, 1, -5, 10)))]
    r = rb(score(tmp_path, rows, [sched(1 + i, kick=k) for i, k in enumerate(kicks)], "2026-11-15", closes=closes))
    assert "primary close: 0 from a later logged quote, 1 from the captured close, 3 with none" in r
    assert f"captured close refused for 3 of these 4 bets: {REFUSED}; counted as missing (1, 2, 3)" in r
    assert "3 of 4 bets without a captured close" in r


def test_a_close_captured_for_the_earlier_listing_of_a_postponed_game_is_not_used_for_the_later_one(tmp_path):
    """The later listing's own capture (58, Oct 31 18:50) is its close, even when the earlier listing's capture (40,
    Oct 10 18:50) comes after it in the file; main took the file's last row, 40."""
    rows = [signal(999, "2026-10-10T19:00Z"), signal(999, "2026-10-31T19:00Z", entry=60.0)]
    closes = [cap(999, "2026-10-31T18:50Z", "2026-10-31T19:00Z", 58.0),
              cap(999, "2026-10-10T18:50Z", "2026-10-10T19:00Z", 40.0)]
    r = rb(score(tmp_path, rows, [sched(999, kick="2026-10-31T19:00Z")], "2026-11-15", closes=closes))
    assert "1 settled, 0 pending, 1 void" in r and "mean CLV +2.00" in r
    assert "1 from the captured close, 0 with none" in r and "refused" not in r


def test_the_window_is_before_the_earlier_of_the_rows_kickoff_and_the_schedules(tmp_path):
    """A game moved earlier, 19:00 on the row to 16:00 in the schedule (not void): a close captured at 18:50 was in
    play and is refused; one captured at 15:50 is used. Two retries in the window: the last in the file is taken."""
    rows = [signal(7, "2026-10-10T19:00Z"), signal(8, "2026-10-17T19:00Z")]
    s = [sched(7, kick="2026-10-10T16:00Z"), sched(8, kick="2026-10-17T16:00Z")]
    closes = [cap(7, "2026-10-10T18:50Z", "2026-10-10T19:00Z", 40.0),
              cap(8, "2026-10-17T15:45Z", "2026-10-17T16:00Z", 49.5), cap(8, "2026-10-17T15:50Z", "2026-10-17T16:00Z",
                                                                          48.5)]
    r = rb(score(tmp_path, rows, s, "2026-11-01", closes=closes))
    assert "2 signals, 2 settled" in r and "mean CLV +2.00" in r
    assert f"captured close refused for 1 of these 2 bets: {REFUSED}; counted as missing (7)" in r


def test_rule_ht_s_secondary_close_is_its_listing_s_too(tmp_path):
    k = "2026-10-10T23:00Z"
    rows = [row(11, k, ts(k) - pd.Timedelta(hours=4), rule_ht="SIGNAL", mkt_total=65.5),
            row(12, k, ts(k) - pd.Timedelta(hours=4), rule_ht="SIGNAL", mkt_total=65.5)]
    closes = [cap(11, ts(k) - pd.Timedelta(minutes=10), k, 64.5), cap(12, ts(k) - pd.Timedelta(minutes=25), k, 60.5)]
    h = ht(score(tmp_path, rows, [sched(11, kick=k), sched(12, kick=k)], "2026-10-20", closes=closes))
    assert "mean CLV vs the captured close +1.00" in h and "1 of 2 bets without a captured close" in h
    assert f"captured close refused for 1 of these 2 bets: {REFUSED}; counted as missing (12)" in h


# ------------------------------------------------------------------ a game moved later on game day (review, finding 1)
ASIDE = "outside the window for the listing, while another inside it is used"


def moved_later(tmp_path, later_row, now="2026-11-01", *extra):
    """Game 21's entry row gives 16:00; the game is moved to 21:00 the same day (under 24 hours: not void). The
    capture job caught both slots: 52.0 at 15:50 for 16:00, and the true close, 47.0, at 20:50 for 21:00. With
    `later_row`, the board logged the game again at 15:00 with the new kickoff (no quote on it, so Rule B's primary
    close is the captured close). Rule HT game 22 is the same, its last quote logged against the kickoff it shows."""
    rows = [signal(21, "2026-10-10T16:00Z", entry=50.5)]
    ht_rows = [row(22, "2026-10-10T16:00Z", "2026-10-10T14:00Z", rule_ht="SIGNAL", mkt_total=65.5)]
    if later_row:
        rows.append(row(21, "2026-10-10T21:00Z", "2026-10-10T15:00Z", mkt_total=np.nan, mkt_under=np.nan))
        ht_rows = [row(22, "2026-10-10T21:00Z", "2026-10-10T15:00Z", rule_ht="SIGNAL", mkt_total=65.5)]
    closes = [cap(21, "2026-10-10T15:50Z", "2026-10-10T16:00Z", 52.0), cap(21, "2026-10-10T20:50Z", "2026-10-10T21:00Z",
                                                                          47.0),
              cap(22, "2026-10-10T15:50Z", "2026-10-10T16:00Z", 66.0), cap(22, "2026-10-10T20:50Z", "2026-10-10T21:00Z",
                                                                          61.0)]
    s = [sched(21, kick="2026-10-10T21:00Z"), sched(22, kick="2026-10-10T21:00Z")]
    return score(tmp_path, rows + ht_rows, s, now, *extra, closes=closes)


def test_a_game_moved_later_is_graded_on_its_true_close_once_a_row_shows_the_new_kickoff(tmp_path):
    """The listing's kickoff is the earlier of its last row's and the schedule's: 21:00, so the close captured at
    20:50 is used (Rule B primary +3.50, Rule HT secondary +4.50, as on main), and the 15:50 capture is set aside,
    counted and named. On the entry row's kickoff alone (the first draft) the stale 15:50 capture was taken."""
    out = moved_later(tmp_path, later_row=True)
    r, h = rb(out), ht(out)
    assert "1 signals, 1 settled, 0 pending, 0 void" in r
    assert "mean CLV +3.50; 1 of 1 bets have a primary close" in r and "1 from the captured close, 0 with none" in r
    assert "secondary (amendment 2): mean CLV vs the captured close +3.50" in r
    assert f"captures set aside for 1 of these 1 bets: 1 {ASIDE} (21)" in r and "refused" not in r
    assert "mean CLV vs the captured close +4.50" in h and f"captures set aside for 1 of these 1 bets: 1 {ASIDE} (22)" in h
    listed = rb(moved_later(tmp_path, True, "2026-11-01", "--list-excluded"))
    line = next(ln for ln in listed.splitlines() if ln.strip().startswith("21 ") and "set aside" in ln)
    assert "2026-10-10T15:50:00Z" in line and "2026-10-10 21:00:00+00:00" in line


def test_a_game_moved_later_with_no_row_after_the_move_is_the_declared_limit_and_is_reported(tmp_path):
    """No row logged after the move: the listing's kickoff is still the entry row's 16:00, so the 15:50 capture (a
    pre-kickoff price for this listing, never in play) is used, and the 20:50 capture is set aside, counted and named."""
    out = moved_later(tmp_path, later_row=False)
    r, h = rb(out), ht(out)
    assert "mean CLV -1.50; 1 of 1 bets have a primary close" in r
    assert f"captures set aside for 1 of these 1 bets: 1 {ASIDE} (21)" in r
    assert "mean CLV vs the captured close -0.50" in h and f"captures set aside for 1 of these 1 bets: 1 {ASIDE} (22)" in h


def test_a_row_logged_after_the_real_kickoff_never_sets_the_listing_s_kickoff(tmp_path):
    """Kickoff 19:00 on the entry row and in the schedule. A row logged at 19:30 that shows 23:00 is excluded as logged
    at or after kickoff (the earlier kickoff bounds it), so the listing's kickoff stays 19:00: a capture at 22:50 (in
    play) is refused; with the 18:50 capture beside it, the 18:50 one is used and the 22:50 one is set aside."""
    rows = [signal(31, "2026-10-10T19:00Z"), row(31, "2026-10-10T23:00Z", "2026-10-10T19:30Z", mkt_total=np.nan,
                                                  mkt_under=np.nan)]
    s = [sched(31, kick="2026-10-10T19:00Z")]
    inplay = cap(31, "2026-10-10T22:50Z", "2026-10-10T23:00Z", 30.0)
    out = score(tmp_path / "a", rows, s, "2026-11-01", closes=[inplay])
    assert "excluded, logged at or after kickoff: 1" in out
    r = rb(out)
    assert "1 with none" in r and f"captured close refused for 1 of these 1 bets: {REFUSED}; counted as missing (31)" in r
    r = rb(score(tmp_path / "b", rows, s, "2026-11-01", closes=[cap(31, "2026-10-10T18:50Z", "2026-10-10T19:00Z", 49.5),
                                                                 inplay]))
    assert "mean CLV +1.00" in r and f"captures set aside for 1 of these 1 bets: 1 {ASIDE} (31)" in r


def test_a_postponed_game_s_earlier_capture_is_still_refused_after_rows_on_the_new_date(tmp_path):
    """Astra's case with the board logging the new listing twice: the Oct 10 capture is still not the Oct 31 listing's
    close (its kickoff comes from the Oct 31 listing's own rows and the schedule)."""
    rows = [signal(999, "2026-10-10T19:00Z"), signal(999, "2026-10-31T19:00Z", entry=60.0),
            row(999, "2026-10-31T19:30Z", "2026-10-31T12:00Z", mkt_total=np.nan, mkt_under=np.nan)]
    closes = [cap(999, "2026-10-10T18:50Z", "2026-10-10T19:00Z", 40.0)]
    r = rb(score(tmp_path, rows, [sched(999, kick="2026-10-31T19:30Z")], "2026-11-15", closes=closes))
    assert "2 signals, 1 settled, 0 pending, 1 void" in r and "1 with none" in r
    assert f"captured close refused for 1 of these 1 bets: {REFUSED}; counted as missing (999)" in r


def test_a_retry_landing_inside_the_last_2_minutes_is_set_aside_and_counted(tmp_path):
    """Review, finding 2: a slot's capture at 18:50 and a retry whose reply landed at 18:58:30 (last in the file): the
    retry is outside the window, so the 18:50 capture is used and the retry is set aside, counted and listed."""
    closes = [cap(41, "2026-10-10T18:50Z", "2026-10-10T19:00Z", 49.5), cap(41, "2026-10-10T18:58:30Z",
                                                                          "2026-10-10T19:00Z", 45.0)]
    args = ([signal(41, "2026-10-10T19:00Z")], [sched(41, kick="2026-10-10T19:00Z")], "2026-11-01")
    r = rb(score(tmp_path, *args, closes=closes))
    assert "mean CLV +1.00" in r and f"captures set aside for 1 of these 1 bets: 1 {ASIDE} (41)" in r
    listed = rb(score(tmp_path, *args, "--list-excluded", closes=closes))
    line = next(ln for ln in listed.splitlines() if ln.strip().startswith("41 ") and "set aside" in ln)
    assert "2026-10-10T18:58:30Z" in line and "45.0" in line


# ------------------------------------------------------------------ the amendment's text
def norm(text):
    return " ".join(text.replace("**", "").replace("`", "").split())


def test_amendment_6_is_registered_and_repairs_registered_rules_and_quotes_what_it_replaces():
    whole = (ROOT / "PREREGISTRATION.md").read_text()
    head, text = whole.split("## Amendment 6 ")[0], whole.split("## Amendment 6 ")[1].split("\n## ")[0]
    assert text.startswith("(registered 2026-09-30 Pacific, before the first eligible game on Oct 1, 2026, 5:00 PM Pacific)")
    assert "by the merge of pull request 90" in text
    assert "DRAFT, not registered" not in text
    assert "To be registered by the hub" not in text
    t = norm(text)
    assert "This amendment repairs two registered rules and changes no threshold, gate or decision rule" in t
    assert "0 variants" in t and "on the day it was written it is 288, so the multiple-testing bar is p < 0.000174" in t
    assert "becomes amendment 7 if the hub registers it" in t and "Nfl-weather amendment 8" in t
    assert "2 to 20 minutes" in t and "both ends included" in t
    assert "earlier of the kickoff on the listing's last row logged before kickoff" in t and "set aside" in t
    bullets = text.split("### What this amendment replaces")[1].split("\n* ")[1:]
    assert len(bullets) == 5
    for bullet in bullets:
        label, rest = bullet.split(': "', 1)
        m = re.match(r"Amendment (\d+)(?:, section (\d+))?", label)
        src = head.split(f"## Amendment {m[1]} ")[1].split("\n## ")[0]
        src = src.split(f"### {m[2]}.")[1].split("\n### ")[0] if m[2] else src
        quotes = re.findall(r'"([^"]+)"', '"' + rest)
        assert quotes, label
        for q in quotes:
            assert norm(q) in norm(src), (label, q)
    status = (ROOT.parent / "STATUS.md").read_text()
    assert status.count("*Amendment 6 (registered Sep 30, PR 90):*") == 2


# ------------------------------------------------------------------ the committed rehearsal ledger
SHIFT = pd.Timedelta(weeks=53)
OFFSETS = [10, 2, 20, 21, 1, 10, 15, 30, 5, 10]       # minutes before kickoff, cycled over the games


def rehearsal(tmp_path, closes):
    """The committed 2025 rehearsal ledger, with the schedule scripts/rehearse_2025.py builds from the committed
    processed games, scored as a preview. With `closes`, one made-up capture per game at the cycled OFFSETS, its
    total half a point above the ledger's last quote."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    src = ROOT / "output" / "tables" / "rehearsal_2025.csv"
    (tmp_path / "ledger.csv").write_bytes(src.read_bytes())
    g = pd.read_parquet(ROOT / "data" / "processed" / "games.parquet")
    g = g[(g.season == 2025) & ((g.home_division == "fbs") | (g.away_division == "fbs")) & g.close_total.notna()
          & g.home_points.notna() & ((g.week >= 5) | (g.season_type == "postseason"))]
    g[["game_id", "home_points", "away_points"]].assign(
        start_utc=(g.start_utc + SHIFT).dt.strftime("%Y-%m-%dT%H:%M:%SZ")).to_csv(tmp_path / "sched.csv", index=False)
    led = pd.read_csv(src)
    last = led.sort_values("snapshot_utc", kind="stable").drop_duplicates("game_id", keep="last")
    off = dict(zip(last.game_id, [OFFSETS[i % len(OFFSETS)] for i in range(len(last))]))
    if closes:
        pd.DataFrame([cap(r.game_id, ts(r.start_utc) - pd.Timedelta(minutes=off[r.game_id]), r.start_utc,
                          r.mkt_total + 0.5) for r in last.itertuples()]).to_csv(tmp_path / "closes.csv", index=False)
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "score_forward.py"), "--ledger",
                          str(tmp_path / "ledger.csv"), "--schedule", str(tmp_path / "sched.csv"), "--now",
                          "2027-03-01"], capture_output=True, text=True, check=True).stdout
    return out, led, off


def test_the_rehearsal_report_is_unchanged_byte_for_byte(tmp_path):
    """No captured closes: the report is the committed rehearsal log's, byte for byte, except its record line (the
    log was a real run on a test ledger; this is a --now preview)."""
    out, _, _ = rehearsal(tmp_path, closes=False)
    log = (ROOT / "output" / "rehearsal_2025.log").read_text()
    logged = log.split("Scorer output (Rule B entry = the opening total, CLV to the close; Rule HT at the close):\n")[1]
    logged = logged.replace("Decision record: the first final decision is written to decisions.csv beside this test "
                            "ledger.", "Decision record: none written by this run: a run with --now is a preview.")
    assert out + "\n" == logged


def test_the_rehearsal_report_changes_only_where_a_captured_close_is_refused(tmp_path):
    """A made-up capture for every game: against the committed log, only the secondary lines change, and a line is
    added naming every refused game, exactly the settled bets whose capture is outside 2 to 20 minutes (21, 1 and 30
    minutes before kickoff; 2 and 20 are used). The secondary mean is recomputed here for Rule B."""
    out, led, off = rehearsal(tmp_path, closes=True)
    base, _, _ = rehearsal(tmp_path / "none", closes=False)
    a, b = base.splitlines(), out.splitlines()
    kept = [ln for ln in b if "captured close refused" not in ln]
    assert len(kept) == len(a)
    changed = [(x, y) for x, y in zip(a, kept) if x != y]
    assert changed and all(x.startswith("  secondary (amendment 2):") and y.startswith("  secondary (amendment 2):")
                           for x, y in changed)
    for part in (rb(out), ht(out)):                                         # each rule's settled bets, named once
        named = [int(s) for m in re.findall(r"counted as missing \(([^)]*)\)", part) for s in m.split(",")]
        settled = {int(g) for g in re.findall(r"^\s*(\d{9})\s", part, re.M)}
        outside = {g for g in settled if not 2 <= off[g] <= 20}
        assert outside and sorted(named) == sorted(outside)
    # Rule B: each signal's earliest SIGNAL row is its entry; CLV against the capture when it is inside the window
    entries = led[led.rule_b == "SIGNAL"].sort_values("snapshot_utc", kind="stable").drop_duplicates("game_id")
    last = led.sort_values("snapshot_utc", kind="stable").drop_duplicates("game_id", keep="last").set_index("game_id")
    inside = entries[[2 <= off[g] <= 20 for g in entries.game_id]]
    clv = inside.mkt_total.to_numpy() - (last.mkt_total.reindex(inside.game_id).to_numpy() + 0.5)
    assert (f"secondary (amendment 2): mean CLV vs the captured close {np.mean(clv):+.2f}" in rb(out)
            and f"{len(entries) - len(inside)} of {len(entries)} bets without a captured close" in rb(out))
