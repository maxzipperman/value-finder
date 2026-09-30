"""Times, kickoffs, STATUS.md and words."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from conftest import PACIFIC, STATUS_MD

from vfdash import status_md, words
from vfdash.data import parse_launchctl_list, parse_launchctl_print, schedule_of, schedule_words

UTC = timezone.utc


@pytest.mark.parametrize("text, expect", [
    ("2026-09-29T14:30:07Z", datetime(2026, 9, 29, 14, 30, 7, tzinfo=UTC)),
    ("2026-09-29T0002Z", datetime(2026, 9, 29, 0, 2, tzinfo=UTC)),
    ("2026-10-02 00:00:00+00:00", datetime(2026, 10, 2, 0, 0, tzinfo=UTC)),
    ("2026-09-28 22:30Z", datetime(2026, 9, 28, 22, 30, tzinfo=UTC)),
    ("", None), ("  ", None), ("nonsense", None), (None, None),
])
def test_parse_utc(text, expect):
    assert words.parse_utc(text) == expect


def test_kickoffs():
    assert words.eastern_kickoff("2026-10-04", "13:00") == datetime(2026, 10, 4, 17, 0, tzinfo=UTC)
    assert words.eastern_kickoff("2026-12-06", "13:00") == datetime(2026, 12, 6, 18, 0, tzinfo=UTC)   # EST
    assert words.eastern_kickoff("", "13:00") is None
    logged = datetime(2026, 9, 29, 14, 30, tzinfo=UTC)
    assert words.cfb_kickoff("2026-10-02 00:00:00+00:00", "Thu 10-01 20:00", logged) == datetime(2026, 10, 2, 0, 0,
                                                                                                 tzinfo=UTC)
    assert words.cfb_kickoff("", "Thu 10-01 20:00", logged) == datetime(2026, 10, 2, 0, 0, tzinfo=UTC)
    dec = datetime(2026, 12, 20, 14, 30, tzinfo=UTC)
    assert words.cfb_kickoff("", "Fri 01-01 13:00", dec) == datetime(2027, 1, 1, 18, 0, tzinfo=UTC)
    assert words.cfb_kickoff("", "", logged) is None


def test_working_hours():
    t = lambda d, h, m=0: datetime(2026, 10, d, h, m, tzinfo=PACIFIC)      # noqa: E731
    assert words.working_hours_between(t(2, 7, 30), t(2, 10), PACIFIC) == pytest.approx(2.5)
    assert words.working_hours_between(t(1, 19, 30), t(2, 7, 30), PACIFIC) == pytest.approx(4.0)
    assert words.working_hours_between(t(1, 19, 30), t(2, 8, 31), PACIFIC) == pytest.approx(5 + 1 / 60)
    assert words.working_hours_between(t(2, 0, 0), t(2, 6, 0), PACIFIC) == 0.0
    assert words.working_hours_between(t(2, 10), t(2, 9), PACIFIC) == 0.0
    # across the end of daylight saving time (Nov 1, 2026): still counted on the wall clock
    assert words.working_hours_between(t(31, 19, 30), datetime(2026, 11, 1, 8, 30, tzinfo=PACIFIC), PACIFIC) == 5.0


def test_next_run():
    times = [(7, 30), (11, 30), (15, 30), (19, 30)]
    at = lambda h, m=0: datetime(2026, 10, 2, h, m, tzinfo=PACIFIC)           # noqa: E731
    assert words.next_run(times, at(10), PACIFIC).strftime("%H:%M") == "11:30"
    assert words.next_run(times, at(11, 30), PACIFIC).strftime("%H:%M") == "15:30"
    nxt = words.next_run(times, at(21), PACIFIC)
    assert (nxt.day, nxt.strftime("%H:%M")) == (3, "07:30")
    assert words.next_run([], at(10), PACIFIC) is None


def test_display_words():
    t = datetime(2026, 9, 29, 14, 30, tzinfo=UTC)
    assert words.clock(t, PACIFIC) == "7:30 AM"
    assert words.when(t, PACIFIC, t) == "7:30 AM"
    assert words.when(t, PACIFIC, datetime(2026, 9, 30, 14, 30, tzinfo=UTC)) == "Tue Sep 29, 7:30 AM"
    assert words.kickoff_et(datetime(2026, 10, 2, 0, 15, tzinfo=UTC)) == "Thu Oct 1, 8:15 PM ET"
    assert words.odds("-108.0") == "−108" and words.odds("105") == "+105" and words.odds("") == ""
    assert words.total("43") == "43.0" and words.pct("0.4855") == "49%"
    assert words.pct("0.10848", signed=True, digits=1) == "+10.8%"
    assert words.pct("-0.02", signed=True, digits=1) == "−2.0%"
    assert words.status_words("rule_ht", "below_threshold", "", "62.617539") == "Total below 62.6"
    assert words.status_words("rule_b", "made_up_value") == "Logged as “made_up_value”"
    assert words.is_signal("rule_b", "SIGNAL_SECONDARY") and not words.is_signal("lean", "UNDER lean")
    assert words.alert_words("ruleb_price_too_high") == "Wind watch, no bet (wind trigger, price too high)"
    assert words.alert_words("lag17") == "Line lag watch (wind 17 mph)"
    # cfb-weather amendment 6 (draft): a Rule HT game with no kickoff time set
    assert words.status_words("rule_ht", "time_tbd") == "Would signal, but no kickoff time is set (not eligible yet)"
    assert words.alert_words("ht_time_tbd") == "Rule HT: not eligible, no kickoff time set"
    assert not words.is_signal("rule_ht", "time_tbd")
    assert words.scrub("error: apiKey=abc123&x=1 token: zzz") == "error: apiKey=***&x=1 token: ***"


def test_waiting_items_and_variants():
    now = datetime(2026, 10, 2, 17, 0, tzinfo=UTC)
    items = status_md.waiting_items(STATUS_MD, now, PACIFIC)
    assert [i["n"] for i in items] == [1, 2, 3, 4]
    assert items[1]["due_iso"] == "2026-10-20"
    assert items[2]["due_iso"] == "2026-09-30" and items[2]["due_level"] == "fail"
    assert status_md.variants(STATUS_MD) == 271
    assert status_md.bar(271) == "0.000185" and status_md.bar(232) == "0.000216" and status_md.bar(None) is None
    assert status_md.variants("no bullet here") is None


@pytest.mark.parametrize("text, expect", [
    ("**X.** Pay it, due Thu Oct 8.", date(2026, 10, 8)),
    ("**X.** due by October 12, 2026", date(2026, 10, 12)),
    ("**X.** due 2026-11-01 at the latest", date(2026, 11, 1)),
    ("**X.** due: Jan 5", date(2027, 1, 5)),
    ("**X.** until Thu Oct 1, 5:00 PM Pacific", None),
    ("**X.** the reads due soon", None),
])
def test_due_dates(text, expect):
    assert status_md.due_date(text, date(2026, 10, 2) if expect != date(2027, 1, 5) else date(2026, 12, 20)) == expect


def test_real_status_md_parses():
    from pathlib import Path
    real = Path(__file__).resolve().parents[2] / "STATUS.md"
    if not real.exists():
        pytest.skip("no STATUS.md in this checkout")
    text = real.read_text()
    items = status_md.waiting_items(text, datetime(2026, 9, 29, 17, 0, tzinfo=UTC), PACIFIC)
    assert len(items) >= 1 and all(i["title"] and i["first_sentence"] for i in items)
    assert isinstance(status_md.variants(text), int)


def test_launchd_parsing():
    listing = "PID\tStatus\tLabel\n-\t0\tcom.nflweather.alerts\n123\t-15\tcom.valuefinder.ledgersync\n-\t0\tother\n"
    assert parse_launchctl_list(listing) == {"com.nflweather.alerts": {"pid": None, "status": 0},
                                             "com.valuefinder.ledgersync": {"pid": 123, "status": -15}}
    printed = "gui/501/x = {\n\tstate = not running\n\truns = 1\n\tlast exit code = (never exited)\n" \
              "\tenvironment = {\n\t\tKEY => secret\n\t}\n}\n"
    assert parse_launchctl_print(printed) == {"state": "not running", "runs": "1", "last exit code": "(never exited)"}
    s = schedule_of({"StartCalendarInterval": [{"Hour": 19, "Minute": 30}, {"Hour": 7, "Minute": 30}],
                     "EnvironmentVariables": {"KEY": "secret"}})
    assert s == {"times": [(7, 30), (19, 30)], "interval": None, "keep_alive": False, "run_at_load": False}
    assert schedule_words(s) == "Twice a day: 7:30 AM and 7:30 PM"
    assert schedule_words(schedule_of({"StartInterval": 900})) == "Every 15 minutes"
    assert schedule_words(None) == "Schedule not known"
