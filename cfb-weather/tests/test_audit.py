"""The Sep 29 independent audit (reviews/2026-09-29-astra-audit.md) listed what the suites did not
establish. One test per gap: board-level line sensitivity, no push on a half-point line, Rule HT's
alert on the true last scheduled run, registered-version rejection, the test window's bounds, the
decision tests, the frozen pricing cohort, and the odds feed's edge cases."""
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cfbweather import board, fetch, quota  # noqa: E402
from cfbweather.market import cohort_hash, cohort_residuals, ev_under, load_games, p_under_at, pricing_cohort  # noqa: E402

RESID = pricing_cohort()
PT = "America/Los_Angeles"


# ------------------------------------------------------------------ the pricing model (D1)
def test_half_point_line_cannot_push_and_a_whole_number_can():
    for line in (40.5, 52.5, 70.5):
        assert float(p_under_at(line, line, RESID)[1]) == 0.0
    win, push = (float(v) for v in p_under_at(52, 52, RESID))
    assert 0.01 < push < 0.06
    assert win + push + (1 - float(p_under_at(52.5, 52, RESID)[0])) == pytest.approx(1.0)


def test_board_prices_the_offered_line_against_the_reference():
    up = pd.DataFrame(dict(mkt_total=[52.5, 52.5, 70.5], mkt_under=[-110.0, -110.0, -110.0],
                           best_line=[53.5, 52.5, np.nan], best_line_under=[-110.0, -105.0, np.nan]))
    out = board.price(up, RESID)
    assert (out.ref_total == out.mkt_total).all()
    assert out.ev_best_line[0] > out.ev_under[0] and out.ev_best_line[1] > out.ev_under[1]
    assert out.ev_under[0] == out.ev_under[2]               # flat in the size of the total (registered)
    assert np.isnan(out.ev_best_line[2])
    assert float(ev_under(50.5, -115, 52.5, RESID)[0]) < 0 < float(ev_under(52.5, -115, 52.5, RESID)[0])


def test_frozen_pricing_cohort():
    assert cohort_hash(RESID) == board.PRICING_COHORT_SHA256 and len(RESID) == 855
    hist = load_games(2006, board.PRICING_LAST_SEASON)
    now = cohort_residuals(hist, (hist.outdoor == 1) & (hist.wx_wind >= board.RULE_B_WIND))
    assert cohort_hash(now) == board.PRICING_COHORT_SHA256, "games.parquet moved; the frozen file did not"


# ------------------------------------------------------------------ Rule HT alerts on the last scheduled run (D3)
def at(local):
    return pd.Timestamp(local, tz=PT).tz_convert("UTC")


@pytest.mark.parametrize("now,kick,last", [
    ("2026-10-10 11:30", "2026-10-10 16:00", False),      # the audit's case: 15:30 still comes before kickoff
    ("2026-10-10 15:30", "2026-10-10 16:00", True),
    ("2026-10-10 11:30", "2026-10-10 15:30", True),       # a run at kickoff can't log a pre-kickoff quote
    ("2026-10-10 19:30", "2026-10-10 21:00", True),       # nothing runs again until 7:30 the next morning
    ("2026-10-10 19:30", "2026-10-11 09:00", False),      # 7:30 tomorrow comes first
    ("2026-10-10 13:00", "2026-10-10 15:00", True),       # a manual run between scheduled ones
    ("2026-10-10 16:30", "2026-10-10 16:00", False),      # already kicked off
])
def test_ht_alert_waits_for_the_last_scheduled_run(now, kick, last):
    assert board.is_last_run_before(at(kick), at(now), tz=PT) is last


def test_exactly_one_scheduled_run_is_the_last_before_any_kickoff():
    day = pd.Timestamp("2026-10-10", tz=PT)
    runs = [day + pd.Timedelta(days=d, hours=h, minutes=m) for d in (-1, 0) for h, m in board.RUN_TIMES]
    for minutes in range(8 * 60, 23 * 60, 7):
        kick = (day + pd.Timedelta(minutes=minutes)).tz_convert("UTC")
        hits = [r for r in runs if board.is_last_run_before(kick, r.tz_convert("UTC"), tz=PT)]
        assert len(hits) == 1, (minutes, hits)


def test_run_times_match_the_installed_schedule():
    sh = (ROOT / "scripts" / "install_alerts.sh").read_text()
    found = re.findall(r"<key>Hour</key><integer>(\d+)</integer><key>Minute</key><integer>(\d+)</integer>", sh)
    assert tuple((int(h), int(m)) for h, m in found) == board.RUN_TIMES


def test_season_of_puts_the_january_title_game_in_the_season_it_ends():
    assert board.season_of("2026-10-07T00:00:00Z") == 2026 and board.season_of("2028-01-10T00:30:00Z") == 2027
    assert board.season_of("2028-08-30T00:00:00Z") == 2028


# ------------------------------------------------------------------ the odds feed
NAMES = {"Troy Trojans": "Troy", "Southern Miss Golden Eagles": "Southern Miss"}


def book(key, point, under, over=-110, stamp="2026-10-06T20:00:00Z"):
    outs = [dict(name="Over", price=over, point=point)]
    if under is not None:
        outs.append(dict(name="Under", price=under, point=point))
    return dict(key=key, markets=[dict(key="totals", last_update=stamp, outcomes=outs)])


def event(books, home="Troy Trojans", away="Southern Miss Golden Eagles"):
    return dict(id="e1", home_team=home, away_team=away, commence_time="2026-10-07T00:00:00Z", bookmakers=books)


def test_rule_quote_needs_a_complete_under_and_falls_back_to_draftkings():
    ev = event([book("pinnacle", 55.5, None), book("draftkings", 56.0, -112)])      # Pinnacle lists no under price
    r = fetch.parse_odds_api([ev], NAMES, "s").iloc[0]
    assert (r.line_src, r.mkt_total, r.mkt_under) == ("draftkings", 56.0, -112)


def test_best_line_and_provider_update_time():
    ev = event([book("pinnacle", 55.5, -110, stamp="2026-10-06T19:58:00Z"), book("fanduel", 56.5, -108),
                book("bovada", 57.0, -125), book("betmgm", 55.5, -104)])
    r = fetch.parse_odds_api([ev], NAMES, "s").iloc[0]
    assert (r.line_src, r.mkt_total, r.quote_update) == ("pinnacle", 55.5, "2026-10-06T19:58:00Z")
    assert (r.best_under, r.best_under_book) == (-104, "betmgm")                    # same total, better price
    assert (r.best_line, r.best_line_under, r.best_line_book) == (56.5, -108, "fanduel")   # 57.0 costs -125


def test_unmatched_team_names_are_recorded():
    ev = event([book("pinnacle", 55.5, -110)], home="Nowhere State Owls")
    out = fetch.parse_odds_api([ev], NAMES, "s")
    assert fetch.LAST_UNMAPPED == ["Nowhere State Owls"] and out.home_team.isna().all()
    fetch.parse_odds_api([event([book("pinnacle", 55.5, -110)])], NAMES, "s")
    assert fetch.LAST_UNMAPPED == []


def test_espn_connection_error_means_no_espn_prices(monkeypatch):
    import requests

    def boom(*a, **k):
        raise requests.ConnectionError("down")
    monkeypatch.setattr(fetch.session, "get", boom)
    assert fetch.espn_week_odds(1).empty


def test_close_capture_counts_as_a_scheduled_job(monkeypatch):
    for label, want in (("com.cfbweather.alerts", True), ("com.valuefinder.closecapture", True),
                        ("com.valuefinder.triggerpoll", False)):
        monkeypatch.setenv("XPC_SERVICE_NAME", label)
        assert quota.scheduled() is want


# ------------------------------------------------------------------ the scorer (D2)
ROW = dict(rules_version="cfb-v3-2026-09-28", kick_et="Sat 10-10 15:30", away_team="A", home_team="B", venue="V",
           lead_days=2, wx_src="forecast", wx_wind=18, wx_temp=60, wx_precip=0, line_src="pinnacle", mkt_over=-110,
           ev_under=0.06, rule_b="no_trigger", best_under=None, best_under_book="", ht_threshold=62.6175,
           rule_ht="below_threshold", mkt_total=50.5, mkt_under=-110, start_utc="2026-10-10T19:30:00Z",
           snapshot_utc="2026-10-08T14:30:00Z")


def score(tmp_path, rows, sched):
    pd.DataFrame(rows).to_csv(tmp_path / "ledger.csv", index=False)
    pd.DataFrame(sched).to_csv(tmp_path / "sched.csv", index=False)
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "score_forward.py"), "--ledger",
                           str(tmp_path / "ledger.csv"), "--schedule", str(tmp_path / "sched.csv")],
                          capture_output=True, text=True, check=True).stdout


def test_scorer_counts_only_registered_pre_kickoff_rows_inside_the_window(tmp_path):
    ht = dict(ROW, rule_ht="SIGNAL", mkt_total=65.5)
    rows = [dict(ht, game_id=1),
            dict(ht, game_id=2, rules_version="NOT_REGISTERED"),
            dict(ht, game_id=3, start_utc="2028-10-07T19:30:00Z", snapshot_utc="2028-10-07T15:30:00Z"),   # the audit's 2028 game
            dict(ht, game_id=4, snapshot_utc="2026-10-10T20:00:00Z"),                                     # after kickoff
            dict(ht, game_id=5, start_utc="2026-09-26T19:30:00Z", snapshot_utc="2026-09-26T15:30:00Z")]
    out = score(tmp_path, rows, [dict(game_id=i, home_points=30, away_points=31) for i in range(1, 6)])
    assert "ledger rows: 5; in the test: 1" in out
    for reason in ("unregistered rules version: 1", "after the 2027 season: 1", "logged at or after kickoff: 1",
                   "before Oct 1, 2026: 1"):
        assert reason in out
    assert "RULE_HT: 1 signals at the last quote before kickoff, 1 settled" in out
    assert "INTERIM read, decides nothing" in out


def test_rule_b_reports_a_primary_close_that_is_the_entry_itself(tmp_path):
    rows = [dict(ROW, game_id=1, rule_b="SIGNAL"),                                           # its own last quote
            dict(ROW, game_id=2, rule_b="SIGNAL", mkt_total=51.5),
            dict(ROW, game_id=2, rule_b="SIGNAL", mkt_total=50.0, snapshot_utc="2026-10-10T18:30:00Z")]
    out = score(tmp_path, rows, [dict(game_id=1, home_points=20, away_points=20),
                                 dict(game_id=2, home_points=20, away_points=20)])
    assert "RULE_B: 2 signals, 2 settled" in out
    assert "1 of 2 are the entry row itself" in out and "1 were logged more than 6 hours before kickoff" in out
    assert "decision (Rule B" in out and "by price source: {'pinnacle': 2}" in out


def test_break_even_test_is_the_binomial_when_every_price_is_the_same():
    sys.path.insert(0, str(ROOT / "scripts"))
    ns = {}
    src = (ROOT / "scripts" / "score_forward.py").read_text()
    exec(src[src.index("def tail_at_least"):src.index("last = L.dropna")], {"np": np}, ns)
    p = 110 / 210
    assert ns["tail_at_least"](60, [p] * 100) == pytest.approx(stats.binomtest(60, 100, p, alternative="greater").pvalue)
    assert ns["tail_at_least"](0, [p] * 5) == pytest.approx(1.0)
    mixed = ns["tail_at_least"](60, [p] * 50 + [115 / 215] * 50)
    assert ns["tail_at_least"](60, [115 / 215] * 100) > mixed > ns["tail_at_least"](60, [p] * 100)
