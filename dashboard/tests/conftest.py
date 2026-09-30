"""Synthetic fixtures: a repo laid out like the real one, a home folder with launchd files, logs and the credit
file, a fixed clock and a fake runner for the few commands the dashboard may start. Nothing here reads the
real checkout, the real home folder or launchd."""
from __future__ import annotations

import json
import plistlib
import shutil
import threading
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from vfdash import commands
from vfdash.data import Config, Store

PACIFIC = ZoneInfo("America/Los_Angeles")
UTC = timezone.utc
CONTENT = Path(__file__).resolve().parents[1] / "content"
SECRET_KEY = "fake-test-key-SECRET-5f3a9c"      # in the fixture .env files: must never be read or shown
FINGERPRINT = "fp0SECRET0abc"                   # the key fingerprint in the credit file: never shown
PLIST_SECRET = "plist-SECRET-token-77"          # an environment value inside a launchd file: never shown
# Thu Oct 2, 2026, 10:00 AM Pacific: after the 7:30 AM runs, before the 11:30 AM runs
NOW = datetime(2026, 10, 2, 17, 0, tzinfo=UTC)

NFL_HEADER = ("snapshot_utc,rules_version,game_id,gameday,gametime,away_team,home_team,lead_days,wx_src,wx_wind,"
              "wx_temp,wx_precip,wx_snow,line_src,total_line,under_odds,over_odds,p_under,p_market,lean,ev_under,"
              "rule_b,best_under,best_under_book,ref_total,best_line,best_line_under,best_line_book,ev_best_line,"
              "quote_utc,quote_update,wx_hash,wx_fetched_utc,wx_wind_dir,wx_cross,wx_along")
CFB_HEADER = ("snapshot_utc,rules_version,game_id,kick_et,away_team,home_team,venue,lead_days,wx_src,wx_wind,"
              "wx_temp,wx_precip,line_src,mkt_total,mkt_under,mkt_over,ev_under,rule_b,best_under,best_under_book,"
              "ht_threshold,rule_ht,ref_total,best_line,best_line_under,best_line_book,ev_best_line,quote_utc,"
              "quote_update,wx_hash,wx_fetched_utc,wx_wind_dir,start_utc,zz_column_from_the_future")


def nfl_row(snap, gid, day, time, away, home, rule_b, lean="", wind="8.1", src="era5", line_src="pinnacle",
            total="44.5", under="-108", version="v3-2026-09-28", lead="2"):
    return ",".join([snap, version, gid, day, time, away, home, lead, src, wind, "61.2", "0.0", "0.0", line_src, total,
                     under, "-106", "0.52", "0.50", lean, "0.104", rule_b, "-105", "lowvig", total, "45.0", "-110",
                     "fanduel", "0.12", snap, snap, "abc123", snap, "270.0", "1.1", "7.9"])


def cfb_row(snap, gid, kick_et, away, home, rule_b, rule_ht, start, total="55.0", extra="x", src="forecast"):
    return ",".join([snap, "cfb-v3-2026-09-28", gid, kick_et, away, home, '"Stadium, The"', "3", src, "9.9",
                     "70.1", "0.0", "pinnacle", total, "-109.0", "-109.0", "0.08", rule_b, "-108.0", "lowvig",
                     "62.617539", rule_ht, total, total, "-108.0", "lowvig", "0.087", snap, snap, "ffee", snap, "98.0",
                     start, extra])


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


STATUS_MD = """# Value Finder: status

*Updated October 2, 2026*

## Projects

Nothing to see.

## Waiting on you

1. **Odds API plan.** A free key is set in all three `.env` files (Sep 28). Live check:
   - Each alert call costs 1 credit.
     - **Variants:** the plan committed 56 on Sep 28 (191). Then **200**, so p < 0.00025. Then **271**, so new analyses use p < 0.000185 (0.05 / 271).
2. **The Oct 20 gate decisions.** By about Oct 20 the hub brings you three reads. The reads are due Oct 20.
3. **Something overdue ([#9](https://example.invalid/9)).** This one was due Sep 30, 2026. More words.
4. **Scorer readings: amendment 6** (in [`PREREGISTRATION.md`](x)). The hub registered both. Then more.

## Backlog

Nothing.
"""


def make_root(base: Path) -> Path:
    root = base / "repo"
    nfl = root / "nfl-weather" / "data" / "forward"
    cfb = root / "cfb-weather" / "data" / "forward"
    early, late = "2026-10-01T22:30:09Z", "2026-10-02T14:30:07Z"
    rows = [
        # an old row from before the ledger was widened: newer columns blank
        "2026-09-28T05:15:21Z,,2026_04_PIT_CLE,2026-10-01,20:15,PIT,CLE,4,era5,10.7,74.9,0.06,0.0,nflverse,38.5,"
        "-115.0,-105.0,0.64,0.51,UNDER lean,,,,,,,,,,,,,,,,",
        nfl_row(early, "2026_04_PIT_CLE", "2026-10-01", "20:15", "PIT", "CLE", "SIGNAL", wind="16.2", lead="0"),
        nfl_row(early, "2026_05_KC_DEN", "2026-10-04", "16:25", "KC", "DEN", "SIGNAL", wind="15.8"),
        nfl_row(late, "2026_05_BUF_NE", "2026-10-04", "13:00", "BUF", "NE", "SIGNAL", wind="17.3"),
        nfl_row(late, "2026_05_KC_DEN", "2026-10-04", "16:25", "KC", "DEN", "no_trigger", wind="12.0"),
        nfl_row(late, "2026_05_TEN_BAL", "2026-10-04", "13:00", "TEN", "BAL", "SIGNAL_SECONDARY", line_src="nflverse",
                wind="18.0"),
        nfl_row(late, "2026_05_ARI_NYG", "2026-10-04", "13:00", "ARI", "NYG", "no_trigger", lean="UNDER lean"),
        nfl_row(late, "2026_05_ATL_NO", "2026-10-05", "20:15", "ATL", "NO", "not_outdoor", src="indoor", wind=""),
    ]
    write(nfl / "ledger.csv", NFL_HEADER + "\n" + "\n".join(rows) + "\n")
    c_early, c_late = "2026-10-01T22:30:17Z", "2026-10-02T14:30:14Z"
    crows = [
        cfb_row(c_early, "401000001", "Fri 10-02 12:00", "Army", "Navy", "no_trigger", "before_window",
                "2026-10-02 16:00:00+00:00"),
        cfb_row(c_late, "401000002", "Sat 10-10 15:30", "Ohio State", "Michigan", "no_trigger", "SIGNAL",
                "2026-10-10 19:30:00+00:00", total="64.5"),
        cfb_row(c_late, "401000003", "Sat 10-03 12:00", "Iowa", "Wisconsin", "no_trigger", "before_window",
                "2026-10-03 16:00:00+00:00"),
        # an older-format row: no start_utc, only the Eastern kickoff
        cfb_row(c_late, "401000004", "Sat 10-03 19:00", "Utah", "BYU", "no_trigger", "before_window", ""),
        cfb_row(c_late, "401000001", "Fri 10-02 12:00", "Army", "Navy", "SIGNAL", "before_window",
                "2026-10-02 16:00:00+00:00"),
    ]
    write(cfb / "ledger.csv", CFB_HEADER + "\n" + "\n".join(crows) + "\n")
    runs = "run_utc,job,rules_version,status,games,signals,priced,unmapped,error,rule_priced\r\n"
    write(nfl / "runs.csv", runs + "2026-10-01T22:30:09Z,nfl-alerts,v3-2026-09-28,ok,6,2,6,,,6\r\n"
                                   "2026-10-02T14:30:07Z,nfl-alerts,v3-2026-09-28,ok,5,2,5,,,4\r\n")
    write(cfb / "runs.csv", runs + "2026-10-02T14:30:14Z,cfb-alerts,cfb-v3-2026-09-28,ok,4,1,4,Some Team,,4\r\n")
    write(nfl / "closes.csv",
          "game_id,kick_utc,home_team,away_team,capture_utc,book,close_total,close_under,close_over,book_update\n"
          "2026_04_PIT_CLE,2026-10-02T00:15:00Z,CLE,PIT,2026-10-02T0002Z,pinnacle,38.0,-106,-106,2026-10-02T00:02:07Z\n"
          "2026_04_PIT_CLE,2026-10-02T00:15:00Z,CLE,PIT,2026-10-02T0002Z,draftkings,38.5,-112,-108,2026-10-02T00:02:07Z\n")
    write(cfb / "closes.csv", "capture_utc,game_id,start_utc,home_team,away_team,line_src,close_total,close_under,"
                              "close_over\n2026-10-02T15:48:00Z,401000001,2026-10-02T16:00:00Z,Navy,Army,pinnacle,"
                              "38.5,-110,-110\n")
    write(nfl / "alert_state.json", json.dumps({"2026_05_BUF_NE": {"sent": ["ruleb", "leanUNDER"], "wind": 17.3,
                                                                   "total": 44.5, "seen_utc": "2026-10-02T14:30Z"},
                                                "2026_05_KC_DEN": {"wind": 12.0, "total": 44.5}}))
    write(cfb / "alert_state.json", json.dumps({"401000001": {"sent": ["ruleb"]}}))
    write(nfl / "alerts.log", "  forecasts: 14 stadium-days\n"
                              "ALERT  RULE B WIND UNDER 44.5 at -108: BUF @ NE 10-04 13:00 ET\n"
                              "       17 mph, 61°F; total 44.5 (pinnacle). apiKey=abcdef0123 Paper only.\n"
                              "2026-10-02 14:30Z checked 5 outdoor games, nothing new\n")
    write(cfb / "alerts.log", "2026-10-02 14:30Z checked 4 FBS games, nothing new\n")
    write(nfl / "fills.csv", "fill_utc,game_id,rule,line,price,book\n2026-10-02T15:05:00Z,2026_05_BUF_NE,rule_b,44.5,"
                             "-108.0,fanduel\n")
    write(cfb / "decisions.csv", "decision_id,rule,horizon,horizon_utc,decided_utc,n_bets,verdict,numbers,ledger_rows,"
                                 "ledger_rows_sha256\nCFB_RULE_B,Rule B,after 40 signals,2026-12-13T08:00:00Z,"
                                 "2026-12-20T10:00:00Z,41,KEEP,{},1 2,"
                                 + "a" * 64 + "\n")
    write(nfl / "ledger.before-v3-2026-09-28.csv", NFL_HEADER + "\n")
    write(root / "STATUS.md", STATUS_MD)
    write(root / "ops" / "RUN_RECORDS.md", "# Run records\n\nKeys are blanked (`apiKey=***`).\n")
    # secrets that must never be opened
    write(root / "nfl-weather" / ".env", f"ODDS_API_KEY={SECRET_KEY}\n")
    write(root / "cfb-weather" / ".env", f"ODDS_API_KEY={SECRET_KEY}\n")
    write(root / ".env", f"ODDS_API_KEY={SECRET_KEY}\n")
    return root


def make_home(base: Path, remaining=491, quota_utc="2026-10-02T14:30:14Z") -> Path:
    home = base / "home"
    agents = home / "Library" / "LaunchAgents"
    agents.mkdir(parents=True, exist_ok=True)
    times = [{"Hour": h, "Minute": 30} for h in (7, 11, 15, 19)]
    for label, extra in (("com.nflweather.alerts", {"StartCalendarInterval": times}),
                         ("com.cfbweather.alerts", {"StartCalendarInterval": times}),
                         ("com.valuefinder.closecapture", {"StartInterval": 900, "RunAtLoad": True}),
                         ("com.valuefinder.ledgersync", {"StartCalendarInterval": {"Hour": 23, "Minute": 45},
                                                         "EnvironmentVariables": {"ODDS_API_KEY": PLIST_SECRET}})):
        (agents / f"{label}.plist").write_bytes(plistlib.dumps({"Label": label, "ProgramArguments": ["/bin/true"],
                                                                **extra}))
    logs = home / "Library" / "Logs"
    write(logs / "valuefinder-closecapture.log", "2026-10-02 00:02Z close capture: 1/1 games priced for "
                                                 "2026-10-02T00:15Z\n")
    write(logs / "valuefinder-ledgersync.log", "ledgers unchanged\nledgers pushed\n")
    quota = {"utc": quota_utc, "project": "cfb-weather", "status": 200, "last": 1, "used": 9,
             "remaining": remaining, "key": FINGERPRINT}
    write(home / ".cache" / "value-finder" / "odds_quota.json", json.dumps(quota))
    write(home / ".cache" / "value-finder" / ".env", f"ODDS_API_KEY={SECRET_KEY}\n")
    return home


NFL_SCORE = """ledger rows: 8; in the test: 0
  excluded, before Week 5 (Oct 8, 2026): 8

MODEL_LEAN: 0 signals, 0 settled, 0 pending, 0 void (not graded)

RULE_B (wind under): 3 signals, 1 settled, 2 pending, 0 void (not graded)

RULE_B, secondary price (not part of the decision): 1 signals
Variants under forward test: 2 (MODEL_LEAN, RULE_B).
"""
CFB_SCORE = """ledger rows: 5; in the test: 5

RULE_B: 1 signals, 0 settled, 1 pending, 0 void (not graded)

RULE_HT: 0 signals at the last quote before kickoff, 0 settled, 0 pending, 0 void (not graded)
"""
LIST_OK = ("PID\tStatus\tLabel\n-\t0\tcom.nflweather.alerts\n-\t0\tcom.cfbweather.alerts\n"
           "-\t0\tcom.valuefinder.closecapture\n-\t0\tcom.valuefinder.ledgersync\n-\t-9\tcom.apple.weatherd\n")
PRINT_OK = ("gui/501/x = {\n\tactive count = 0\n\tstate = not running\n\truns = 3\n\tlast exit code = 0\n"
            "\tenvironment = {\n\t\tODDS_API_KEY => " + PLIST_SECRET + "\n\t}\n}\n")


# ---------------------------------------------------------------- the scorers' --json documents, as fixtures
def bet(gid, away, home, kick, logged, line, price, src, outcome, close=None, close_src=None, close_from=None,
        clv=None, final=None, units=None, void_reason=None, side="UNDER", assumed=False, captured=None):
    """One bet as a scorer's document gives it."""
    return {"game_id": gid, "away_team": away, "home_team": home, "kickoff_utc": kick, "entry_row_kickoff_utc": kick,
            "side": side, "logged_utc": logged, "entry_line": line, "entry_price": price, "price_assumed": assumed,
            "price_source": src, "close_line": close, "close_source": close_src, "close_from": close_from, "clv": clv,
            "captured_close": captured, "clv_captured": None, "final_total": final, "outcome": outcome,
            "void_reason": void_reason, "units": units, "ledger_row": 1, "listing": 0}


def doc_test(tid, name, bets, decisions=(), interval=None, **extra):
    """One test as a scorer's document gives it; its numbers worked out from its bets, as the scorer prints them."""
    settled = [b for b in bets if b["outcome"] in ("won", "lost", "push")]
    won = sum(b["outcome"] == "won" for b in settled)
    pushed = sum(b["outcome"] == "push" for b in settled)
    units = sum(b["units"] for b in settled)
    clvs = [b["clv"] for b in settled if b["clv"] is not None]
    void = [b for b in bets if b["outcome"] == "void"]
    reasons = {}
    for b in void:
        reasons[b["void_reason"]] = reasons.get(b["void_reason"], 0) + 1
    return {"id": tid, "name": name, "printed_as": tid, "decides": True,
            "counts": {"signals": len(bets), "settled": len(settled),
                       "pending": sum(b["outcome"] == "pending" for b in bets), "void": len(void)},
            "void_reasons": reasons,
            "record": {"won": won, "lost": len(settled) - won - pushed, "pushed": pushed} if settled else None,
            "units": units if settled else None, "roi_percent": 100 * units / len(settled) if settled else None,
            "graded_at_assumed_price": 0 if settled else None, "mean_clv": sum(clvs) / len(clvs) if clvs else None,
            "n_clv": len(clvs) if settled else None, "interval": interval, "secondary_clv": None,
            "decisions": list(decisions), "bets": bets} | extra


def scorer_doc(project, text, tests):
    return {"scorer": project, "generated_utc": "2026-10-02T17:00:00Z", "now": "2026-10-02T17:00:00Z", "preview": True,
            "ledger": f"/repo/{project}/data/forward/ledger.csv", "text": text, "rows": {}, "excluded": {},
            "decision_record": {"written_by_this_run": False, "why_not": "a run with --now is a preview"},
            "tests": tests}


INTERIM = {"id": "RULE_B:2026-27", "name": "Rule B", "status": "interim", "verdict": None,
           "text": "  decision (Rule B): INTERIM read, decides nothing.\n"}
# The default documents agree with the printed reports above (NFL_SCORE, CFB_SCORE)
NFL_DOC = scorer_doc("nfl-weather", NFL_SCORE, [
    doc_test("RULE_B", "Rule B", [
        bet("2026_04_PIT_CLE", "PIT", "CLE", "2026-10-02T00:15:00Z", "2026-10-01T22:30:09Z", 38.5, -108.0, "pinnacle",
            "won", close=38.0, close_src="nflverse schedule", clv=0.5, final=31.0, units=100 / 108),
        bet("2026_05_KC_DEN", "KC", "DEN", "2026-10-04T20:25:00Z", "2026-10-01T22:30:09Z", 44.5, -108.0, "pinnacle",
            "pending"),
        bet("2026_05_BUF_NE", "BUF", "NE", "2026-10-04T17:00:00Z", "2026-10-02T14:30:07Z", 44.5, -108.0, "pinnacle",
            "pending")], decisions=[INTERIM]),
    doc_test("RULE_B_SECONDARY", "Rule B, backup price", [
        bet("2026_05_TEN_BAL", "TEN", "BAL", "2026-10-04T17:00:00Z", "2026-10-02T14:30:07Z", 44.5, -108.0, "nflverse",
            "pending")], decides=False),
    doc_test("MODEL_LEAN", "Model lean", [])])
CFB_DOC = scorer_doc("cfb-weather", CFB_SCORE, [
    doc_test("RULE_B", "Rule B", [
        bet("401000001", "Army", "Navy", "2026-10-02T16:00:00Z", "2026-10-02T14:30:14Z", 55.0, -109.0, "pinnacle",
            "pending")]),
    doc_test("RULE_HT", "Rule HT", [])])


# A richer pair of documents, three weeks into the tests (Tue Oct 20, 2026): settled, pending and void bets on both
# sports and both NFL prices, a lean, and Rule HT. Their numbers are worked out by hand in test_signals.py.
LATER = datetime(2026, 10, 20, 17, 0, tzinfo=UTC)          # Tue Oct 20, 10:00 AM Pacific
VOID_MOVED = "the game kicked off more than 24 hours from the kickoff on its entry row"
VOID_OTHER = "another listing of this game is the one graded"
RICH_NFL_DOC = scorer_doc("nfl-weather", "ledger rows: 40; in the test: 40\n", [
    doc_test("RULE_B", "Rule B", [
        bet("2026_06_BUF_NYJ", "BUF", "NYJ", "2026-10-11T17:00:00Z", "2026-10-09T14:30:07Z", 41.5, -108.0, "pinnacle",
            "won", close=40.5, close_src="nflverse schedule", clv=1.0, final=37.0, units=100 / 108),
        bet("2026_06_KC_DEN", "KC", "DEN", "2026-10-11T20:25:00Z", "2026-10-09T14:30:07Z", 44.0, -112.0, "pinnacle",
            "lost", close=44.5, close_src="nflverse schedule", clv=-0.5, final=47.0, units=-1.0),
        bet("2026_07_GB_CHI", "GB", "CHI", "2026-10-18T17:00:00Z", "2026-10-16T14:30:07Z", 39.0, -105.0, "pinnacle",
            "push", close=38.0, close_src="nflverse schedule", clv=1.0, final=39.0, units=0.0),
        bet("2026_08_SF_SEA", "SF", "SEA", "2026-10-25T20:05:00Z", "2026-10-20T14:30:07Z", 42.5, -110.0, "pinnacle",
            "pending"),
        bet("2026_06_MIA_CLE", "MIA", "CLE", "2026-10-13T00:15:00Z", "2026-10-09T14:30:07Z", 40.0, -110.0, "pinnacle",
            "void", void_reason=VOID_MOVED)],
        decisions=[INTERIM], interval={"low": -1.65, "high": 2.65, "n": 3, "game_days": 2, "plain_half_width": 1.9,
                                       "grouped_half_width": 2.15}),
    doc_test("RULE_B_SECONDARY", "Rule B, backup price", [
        bet("2026_06_TEN_IND", "TEN", "IND", "2026-10-11T17:00:00Z", "2026-10-09T14:30:07Z", 43.5, -110.0, "nflverse",
            "won", close=43.0, close_src="nflverse schedule", clv=0.5, final=40.0, units=100 / 110),
        bet("2026_08_NYG_PHI", "NYG", "PHI", "2026-10-25T17:00:00Z", "2026-10-20T14:30:07Z", 45.0, None, "nflverse",
            "pending", assumed=True)], decides=False),
    doc_test("MODEL_LEAN", "Model lean", [
        bet("2026_06_LV_LAC", "LV", "LAC", "2026-10-11T20:05:00Z", "2026-10-05T14:30:07Z", 47.5, -110.0, "pinnacle",
            "won", close=48.0, close_src="nflverse schedule", clv=0.5, final=51.0, units=100 / 110, side="OVER")])])
RICH_CFB_DOC = scorer_doc("cfb-weather", "ledger rows: 60; in the test: 60\n", [
    doc_test("RULE_B", "Rule B", [
        bet("401000101", "Iowa", "Wisconsin", "2026-10-03T16:00:00Z", "2026-10-01T14:30:14Z", 44.5, -109.0, "pinnacle",
            "won", close=43.5, close_src="pinnacle", close_from="later quote", clv=1.0, final=30.0, units=100 / 109),
        bet("401000102", "Army", "Navy", "2026-10-10T19:30:00Z", "2026-10-08T14:30:14Z", 38.5, -110.0, "draftkings",
            "lost", close=39.0, close_src="captured close (pinnacle)", close_from="captured close", clv=-0.5,
            final=45.0, units=-1.0),
        bet("401000103", "Utah", "BYU", "2026-10-24T19:30:00Z", "2026-10-20T14:30:14Z", 47.0, -108.0, "pinnacle",
            "pending"),
        bet("401000104", "Duke", "Wake Forest", "2026-10-17T16:00:00Z", "2026-10-15T14:30:14Z", 51.0, -110.0,
            "pinnacle", "void", void_reason=VOID_OTHER)]),
    doc_test("RULE_HT", "Rule HT", [
        bet("401000201", "Ohio State", "Michigan", "2026-10-10T19:30:00Z", "2026-10-10T14:30:14Z", 64.5, -110.0,
            "pinnacle", "won", final=55.0, units=100 / 110, captured=63.5),
        bet("401000202", "Texas", "Oklahoma", "2026-10-10T16:00:00Z", "2026-10-10T14:30:14Z", 66.0, -112.0,
            "pinnacle", "lost", final=70.0, units=-1.0),
        bet("401000203", "USC", "Oregon", "2026-10-24T23:00:00Z", "2026-10-20T14:30:14Z", 65.5, -110.0, "pinnacle",
            "pending")])])


def rich_store(root: Path, home: Path, runner=None, clock=None) -> Store:
    """The fixtures three weeks on, with the rich documents; one college game (Utah at BYU, 401000103) is still to
    kick off and its newest row is a Rule B signal."""
    with (root / "cfb-weather" / "data" / "forward" / "ledger.csv").open("a") as f:
        f.write(cfb_row("2026-10-20T14:30:14Z", "401000103", "Sat 10-24 15:30", "Utah", "BYU", "SIGNAL", "no_price",
                        "2026-10-24 19:30:00+00:00", total="47.0") + "\n")
    return make_store(root, home, clock=clock or Clock(LATER),
                      runner=runner or FakeRunner(nfl_doc=RICH_NFL_DOC, cfb_doc=RICH_CFB_DOC))


class FakeRunner:
    """Answers the allowed commands with canned output and records every call. A scorer answers with its --json
    document (the printed report as its text); `scorer` says how it fails instead. With `raw` (for the NFL scorer
    only) it prints exactly that, exits 0, and the college scorer answers as usual."""

    def __init__(self, listing=LIST_OK, scorer="ok", nfl_text=NFL_SCORE, cfb_text=CFB_SCORE,
                 stderr="Traceback ...\nValueError: boom", nfl_doc=None, cfb_doc=None, raw=None):
        self.listing, self.scorer, self.nfl_text, self.cfb_text = listing, scorer, nfl_text, cfb_text
        self.docs = {"nfl-weather": nfl_doc or NFL_DOC, "cfb-weather": cfb_doc or CFB_DOC}
        self.stderr, self.raw = stderr, raw
        self.calls = []
        self.lock = threading.Lock()

    def __call__(self, cmd, cwd, timeout):
        with self.lock:
            self.calls.append((list(cmd), cwd, timeout))
        if cmd == commands.launchctl_list_command():
            if self.listing is None:
                return commands.Result(ok=False, code=1)
            return commands.Result(ok=True, stdout=self.listing, code=0)
        if cmd[:2] == [commands.LAUNCHCTL, "print"]:
            return commands.Result(ok=True, stdout=PRINT_OK, code=0)
        if cmd[1] == commands.SCORER:
            project = "nfl-weather" if cwd.endswith("nfl-weather") else "cfb-weather"
            text = self.nfl_text if project == "nfl-weather" else self.cfb_text
            if self.raw is not None and project == "nfl-weather":
                return commands.Result(ok=True, stdout=self.raw, code=0, seconds=0.1)
            if self.scorer == "ok":
                doc = dict(self.docs[project], text=text)
                return commands.Result(ok=True, stdout=json.dumps(doc), code=0, seconds=0.1)
            if self.scorer == "not_document":             # it ran, but printed its report, not the document
                return commands.Result(ok=True, stdout=text, code=0, seconds=0.1)
            if self.scorer == "timeout":
                return commands.Result(ok=False, stdout="ledger rows: 8", timed_out=True, seconds=60)
            if self.scorer == "missing":
                return commands.Result(ok=False, missing=True)
            if self.scorer == "failed_after_printing":
                return commands.Result(ok=False, stdout=text, stderr=self.stderr, code=1)
            return commands.Result(ok=False, stdout="", stderr=self.stderr, code=1)
        raise AssertionError(f"unexpected command {cmd!r}")


class Clock:
    def __init__(self, t=NOW):
        self.t = t

    def __call__(self):
        return self.t


def make_store(root: Path, home: Path, clock=None, runner=None, content: Path = CONTENT,
               scorer_root: Path | None = None) -> Store:
    cfg = Config(root=root, scorer_root=scorer_root or root, home=home, content=content, tz=PACIFIC, port=0)
    return Store(cfg, clock=clock or Clock(), runner=runner or FakeRunner())


@pytest.fixture
def root(tmp_path):
    return make_root(tmp_path)


@pytest.fixture
def home(tmp_path):
    return make_home(tmp_path)


@pytest.fixture
def runner():
    return FakeRunner()


@pytest.fixture
def store(root, home, runner):
    return make_store(root, home, runner=runner)


class Running:
    """A real server on 127.0.0.1 and a free port, for the duration of a test."""

    def __init__(self, store):
        from vfdash.server import make_server
        self.server = make_server(store, "127.0.0.1", 0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def get(self, path, headers=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def json(self, path):
        status, body, _ = self.get(path)
        return status, json.loads(body)

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def served(store):
    s = Running(store)
    yield s
    s.close()


ENDPOINTS = ["/api/summary", "/api/home", "/api/board", "/api/game?id=2026_05_BUF_NE", "/api/game?id=401000002",
             "/api/signals", "/api/backtests", "/api/tests", "/api/jobs", "/api/run-records", "/api/pull", "/api/research"]


def copy_content(dst: Path) -> Path:
    shutil.copytree(CONTENT, dst)
    return dst
