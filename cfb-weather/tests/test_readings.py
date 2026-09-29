"""Amendment 4: the scorer readings that a review of pull request 50 found open. One test per reading,
built on the reviewers' own scenarios (their inputs are reused here). Each test fails on the scorer as
merged in pull request 50 and passes under amendment 4."""
import hashlib
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cfbweather import board  # noqa: E402
from cfbweather.market import ev_under, p_under_at, pricing_cohort  # noqa: E402

COLUMNS = ["rule", "horizon", "horizon_utc", "decided_utc", "n_bets", "verdict", "numbers", "ledger_rows_sha256"]


def ts(x):
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def row(gid, kick, snap, **kw):
    base = dict(rules_version="cfb-v3-2026-09-28", game_id=gid, kick_et="x", away_team="A", home_team="B", venue="V",
                lead_days=2, wx_src="forecast", wx_wind=18, line_src="pinnacle", mkt_total=50.5, mkt_under=-110,
                mkt_over=-110, ev_under=0.06, ht_threshold=62.6175, rule_b="no_trigger", rule_ht="below_threshold",
                start_utc=ts(kick).strftime("%Y-%m-%dT%H:%M:%SZ"), snapshot_utc=ts(snap).strftime("%Y-%m-%dT%H:%M:%SZ"))
    return base | kw


def sched(gid, hp=20, ap=20, completed=True, kick=None):
    s = dict(game_id=gid, home_points=hp, away_points=ap, completed=completed)
    return s | ({"start_date": ts(kick).strftime("%Y-%m-%dT%H:%M:%S.000Z")} if kick else {})


def rb_signals(n, first="2026-10-03T19:00Z", every_days=1, first_id=1, entry=50.5, close=49.5, hp=20, ap=20):
    """`n` Rule B signals: an entry row 2 days out and, unless `close` is None, a later quote 3 hours out."""
    rows, s = [], []
    for i in range(n):
        k = ts(first) + pd.Timedelta(days=every_days * i)
        rows.append(row(first_id + i, k, k - pd.Timedelta(days=2), rule_b="SIGNAL", mkt_total=entry))
        if close is not None:
            rows.append(row(first_id + i, k, k - pd.Timedelta(hours=3), mkt_total=close))
        s.append(sched(first_id + i, hp, ap, kick=k))
    return rows, s


def ht_bet(gid, kick, under=-110, total=65.5, snap_h=4, **kw):
    return row(gid, kick, ts(kick) - pd.Timedelta(hours=snap_h), rule_ht="SIGNAL", mkt_total=total, mkt_under=under,
               **kw)


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


# ------------------------------------------------------------------ reading 1: void
def test_reading_1_a_postponed_or_never_scored_game_is_void(tmp_path):
    """The reviewers' postponed game: logged for Oct 10, played Oct 31 under the same id, graded 0-1."""
    rows = [row(77, "2026-10-10T19:30Z", "2026-10-08T14:30Z", rule_b="SIGNAL"),
            row(78, "2026-10-17T19:30Z", "2026-10-15T14:30Z", rule_b="SIGNAL"),
            row(79, "2026-10-24T19:30Z", "2026-10-22T14:30Z", rule_b="SIGNAL")]
    s = [sched(77, 35, 31, kick="2026-10-31T19:30Z"),                          # postponed three weeks
         sched(78, np.nan, np.nan, completed=False, kick="2026-10-17T19:30Z"),  # never scored
         sched(79, 20, 20, kick="2026-10-24T23:30Z")]                          # 4 hours late: still a bet
    out = rb(score(tmp_path, rows, s, "2026-11-20"))
    assert "3 signals, 1 settled, 0 pending, 2 void (not graded)" in out
    assert "void, the game kicked off more than 24 hours from the kickoff on its entry row: 1 (77)" in out
    assert "void, the schedule shows no result 30 days after that kickoff: 1 (78)" in out
    assert "record 1-0-0" in out


# ------------------------------------------------------------------ reading 2: pending
def test_reading_2_a_signal_still_waiting_for_its_score_holds_the_decision_open(tmp_path):
    """The reviewers' C2: a week after kickoff the old scorer treated an unscored game as never played."""
    rows, s = rb_signals(41)
    bad, sb = rb_signals(1, first="2026-12-12T19:00Z", first_id=900, close=56.5)
    waiting = [dict(x, home_points=np.nan, away_points=np.nan, completed=False) for x in sb]
    out = rb(score(tmp_path, rows + bad, s + waiting, "2026-12-21"))
    assert "42 signals, 41 settled, 1 pending, 0 void" in out
    assert "INTERIM read, decides nothing. Its horizon has passed: 2026-12-12" in out
    assert "The decision waits for 1 pending signal." in out
    assert "FINAL" not in out and not (tmp_path / "decisions.csv").exists()


# ------------------------------------------------------------------ reading 3: decided once, written down
def test_reading_3_the_first_final_decision_is_written_down_and_stands(tmp_path):
    """The reviewers' L1/L2: three Dec 12 signals whose scores land late turned KEEP into a drop."""
    g, sg = [], []
    for i in range(40):
        r, s1 = rb_signals(1, first=ts("2026-10-03T19:00Z") + pd.Timedelta(days=i), first_id=1 + i,
                           close=49.5 if i % 2 == 0 else 50.5)
        g, sg = g + r, sg + s1
    b, sb = rb_signals(3, first="2026-12-12T17:00Z", every_days=0, first_id=900, close=56.5)
    late = [dict(x, home_points=np.nan, away_points=np.nan, completed=False) for x in sb]
    first = rb(score(tmp_path, g + b, sg + late, "2027-01-12"))             # 31 days on: the three are void
    assert "43 signals, 40 settled, 0 pending, 3 void" in first
    assert "FINAL: KEEP, on the 40 signals that kicked off by 2026-12-12, the end of the regular season" in first

    rec = pd.read_csv(tmp_path / "decisions.csv", dtype=str)
    assert list(rec.columns) == COLUMNS and len(rec) == 1
    r = rec.iloc[0]
    assert (r.rule, r.n_bets, r.verdict, r.decided_utc) == ("Rule B", "40", "KEEP", "2027-01-12T00:00:00Z")
    assert r.horizon == "after 40 signals or the 2026 regular season, whichever is later"
    lines = (tmp_path / "ledger.csv").read_text().splitlines()
    entries = [lines[0]] + [ln for ln in lines[1:] if ",SIGNAL," in ln and int(ln.split(",")[1]) <= 40]
    assert r.ledger_rows_sha256 == hashlib.sha256(("\n".join(entries) + "\n").encode()).hexdigest()

    later = rb(score(tmp_path, g + b, sg + sb, "2027-01-20"))               # the scores land
    assert "43 signals, 43 settled, 0 pending, 0 void" in later
    assert "FINAL: KEEP, on the 40 signals that kicked off by 2026-12-12" in later
    assert "recorded in decisions.csv on 2027-01-12T00:00:00Z" in later
    assert "a fresh computation on the same horizon now gives: NOT KEPT" in later and "n=43" in later
    assert "The recorded decision stands." in later and len(pd.read_csv(tmp_path / "decisions.csv")) == 1


def test_reading_3_fewer_than_forty_at_the_end_of_the_test_is_written_down_too(tmp_path):
    """The reviewers' D1/D2: 25 signals when the test ends."""
    rows, s = rb_signals(25, every_days=7)
    for now in ("2028-02-01", "2028-03-01"):                                 # decided, then reprinted
        out = rb(score(tmp_path, rows, s, now))
        assert "decision (Rule B), FINAL: INCONCLUSIVE. The test ended with 25 settled signals, fewer than 40." in out
        assert "recorded in decisions.csv on 2028-02-01T00:00:00Z" in out and "fresh" not in out
    rec = pd.read_csv(tmp_path / "decisions.csv", dtype=str)
    assert len(rec) == 1 and (rec.rule[0], rec.n_bets[0], rec.verdict[0]) == ("Rule B", "25", "INCONCLUSIVE")


# ------------------------------------------------------------------ reading 4: horizons are dates
def test_reading_4_a_game_after_the_title_game_never_counts_and_dec_12_is_named(tmp_path):
    rows, s = rb_signals(40)
    feb = row(500, "2028-02-05T19:00Z", "2028-02-03T19:00Z", rule_b="SIGNAL")   # season label 2027, after Feb 1, 2028
    out = score(tmp_path, rows + [feb], s + [sched(500)], "2026-12-20")
    assert "excluded, after the 2027 season: 1" in out
    assert "40 signals, 40 settled" in rb(out)
    assert "FINAL: KEEP, on the 40 signals that kicked off by 2026-12-12, the end of the regular season" in out


# ------------------------------------------------------------------ reading 9: a quote, and Rule HT's entry
def test_reading_9_rule_ht_enters_at_the_last_quote_with_a_price(tmp_path):
    """The reviewers' H1: a last row with a total and no under price made game 3's bet vanish."""
    k = "2026-10-10T23:00Z"
    rows = [ht_bet(1, k, total=65.5, snap_h=11.5), row(1, k, ts(k) - pd.Timedelta(hours=3.5), mkt_total=62.5),
            ht_bet(2, k, total=66.5, snap_h=11.5), ht_bet(2, k, total=64.5, snap_h=3.5),
            ht_bet(3, k, total=65.5, snap_h=11.5),
            row(3, k, ts(k) - pd.Timedelta(hours=3.5), rule_ht="no_price", mkt_total=65.5, mkt_under=np.nan,
                line_src="espn"),
            ht_bet(4, k, total=65.0)]                                          # scores 65: a push
    out = ht(score(tmp_path, rows, [sched(1), sched(2), sched(3), sched(4, 30, 35)], "2026-10-20"))
    assert "3 signals at the last quote before kickoff, 3 settled" in out
    assert "record 2-0-1" in out and "units +1.82, ROI +60.6% per bet placed" in out
    assert "pushes are left out of the exact test and count in ROI" in out


# ------------------------------------------------------------------ reading 10: Rule B's primary close
def test_reading_10_rule_b_closes_at_a_later_quote_else_the_captured_close_else_none(tmp_path):
    """The reviewers' J (Pinnacle entry, DraftKings close), plus a signal whose only quote is its own row."""
    rows = [row(1, "2026-10-10T19:30Z", "2026-10-08T14:30Z", rule_b="SIGNAL", mkt_total=50.5),
            row(1, "2026-10-10T19:30Z", "2026-10-10T18:30Z", mkt_total=48.5, line_src="draftkings"),
            row(2, "2026-10-17T19:30Z", "2026-10-15T14:30Z", rule_b="SIGNAL", mkt_total=50.5),
            row(3, "2026-10-24T19:30Z", "2026-10-22T14:30Z", rule_b="SIGNAL", mkt_total=50.5),
            row(3, "2026-10-24T19:30Z", "2026-10-24T18:30Z", mkt_total=47.5, mkt_under=-50)]  # not a price
    closes = [dict(capture_utc="2026-10-17T19:20Z", game_id=2, start_utc="2026-10-17T19:30:00Z", home_team="B",
                   away_team="A", line_src="pinnacle", close_total=49.0, close_under=-110, close_over=-110)]
    out = rb(score(tmp_path, rows, [sched(1), sched(2), sched(3)], "2026-11-01", closes=closes))
    assert "mean CLV +1.75" in out and "2 of 3 bets have a primary close" in out
    assert ("primary close: 1 from a later logged quote, 1 from the captured close, 1 with none "
            "(counted, left out of the CLV)") in out
    assert "by price source: {'pinnacle': 3}" in out
    assert "close from: {'draftkings': 1, 'captured close (pinnacle)': 1, 'none': 1}" in out


# ------------------------------------------------------------------ reading 11: not kept
def test_reading_11_not_kept_means_no_money_goes_on_the_rule(tmp_path):
    rows, s = rb_signals(40, close=51.5)                                     # every signal lost a point
    out = rb(score(tmp_path, rows, s, "2026-12-20"))
    assert ("FINAL: NOT KEPT (no money goes on the rule; it stays on paper for 2027 only by a dated amendment "
            "before 2027 Week 0)") in out


# ------------------------------------------------------------------ reading 12: Rule HT by price source
def test_reading_12_rule_ht_is_reported_by_price_source(tmp_path):
    rows = [ht_bet(1, "2026-10-10T23:00Z"), ht_bet(2, "2026-10-17T23:00Z"),
            ht_bet(3, "2026-10-24T23:00Z", line_src="draftkings", under=-105)]
    out = ht(score(tmp_path, rows, [sched(1), sched(2, 40, 40), sched(3)], "2026-11-01"))
    assert "by price source: pinnacle 2 (1-1-0, units -0.09); draftkings 1 (1-0-0, units +0.95)" in out


# ------------------------------------------------------------------ reading 13: amendment 3's numbers
def test_reading_13_amendment_4_quotes_the_models_own_numbers():
    text = (ROOT / "PREREGISTRATION.md").read_text().split("## Amendment 4 ")[1].split("\n## ")[0]
    resid = pricing_cohort(board.PRICING_COHORT_SHA256)
    for line in (42.5, 43.0):                                               # where the value at x = 0 reaches zero
        win, push = (float(np.ravel(v)[0]) for v in p_under_at(line, line, resid))
        assert round(-100 * win / (1 - win - push)) == -130
    assert "about −130" in text

    def ev(below):
        return float(np.ravel(ev_under(42.5 - below, -115, 42.5, resid))[0])
    assert ev(1.5) < 0 < ev(1.0)
    assert "from 1.5 points below the reference" in text
