"""The NBA forward collector (markets.collector), against fake Kalshi and Odds API sessions. No network."""
import csv
import fcntl
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from markets import collector as col

UTC = timezone.utc
TIP = datetime(2026, 10, 21, 23, 30, tzinfo=UTC)
CFG = dict(sport="nba", start=date(2026, 10, 20), window_before_tip_hours=56, window_after_tip_min=15, every_min=5,
           final_minutes=120, final_every_min=None, series_ticker="KXNBAGAME", sport_key="basketball_nba",
           bookmakers=["pinnacle", "lowvig", "betonlineag"], markets="h2h")


class Resp:
    def __init__(self, status, body, headers=None):
        self.status_code, self.text, self.headers = status, json.dumps(body), headers or {}

    def json(self):
        return json.loads(self.text)


class FakeOdds:
    def __init__(self, remaining=4_000_000):
        self.calls, self.remaining = [], remaining

    def get(self, url, params=None, timeout=None, allow_redirects=True):
        self.calls.append(url)
        if url.endswith("/events"):
            return Resp(200, [{"id": "e1", "commence_time": TIP.strftime("%Y-%m-%dT%H:%M:%SZ"),
                               "home_team": "Boston Celtics", "away_team": "New York Knicks"}])
        self.remaining -= 1
        return Resp(200, [{"id": "e1", "bookmakers": []}],
                    {"X-Requests-Last": "1", "X-Requests-Remaining": str(self.remaining),
                     "X-Requests-Used": str(5_000_000 - self.remaining)})


class FakeKalshi:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(dict(params))
        return Resp(200, {"events": [{"event_ticker": "KXNBAGAME-26OCT21NYKBOS", "markets": [{}, {}]}], "cursor": ""})


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(col, "QUOTA_FILE", tmp_path / "quota.json")
    for v in ("ODDS_API_TIER", "ODDS_BACKGROUND_FLOOR"):
        monkeypatch.delenv(v, raising=False)
    # These legacy cadence/cache/quota tests isolate policy from paid admission.
    # ops/collector-safety/test_guard.py exercises the REAL guard with synthetic
    # authority/ledger, including crash, concurrency and missing authority.
    monkeypatch.setattr(col, "paid_get", lambda session, url, params, **kw:
                        session.get(url, params=params, timeout=60, allow_redirects=False))
    odds, kalshi = FakeOdds(), FakeKalshi()
    c = col.Collector(cfg=dict(CFG), data_dir=tmp_path, odds_session=odds, kalshi_session=kalshi, api_key="SECRET")
    c.kalshi.limiter = c.limiter
    return c, odds, kalshi, tmp_path


def paid(tmp_path, remaining=4_000_000, used=1_000_000, now=TIP):
    (tmp_path / "quota.json").write_text(json.dumps(dict(utc=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                                         remaining=remaining, used=used)))


def runs(tmp_path):
    return list(csv.DictReader((tmp_path / "collector" / "nba" / "runs.csv").open()))


def test_nothing_before_the_opener(env):
    c, odds, kalshi, _ = env
    assert c.tick(datetime(2026, 10, 19, 12, tzinfo=UTC)) is None and odds.calls == [] and kalshi.calls == []


def test_collects_inside_the_window_every_five_minutes(env):
    c, odds, kalshi, tmp = env
    now = TIP - timedelta(hours=3)
    paid(tmp, now=now)
    row = c.tick(now)
    assert row["action"] == "collected" and row["kalshi_events"] == 1 and row["kalshi_markets"] == 2
    assert row["odds_status"] == 200 and row["credits_last"] == "1"
    assert kalshi.calls[0]["status"] == "open" and kalshi.calls[0]["with_nested_markets"] == "true"
    assert c.tick(now + timedelta(minutes=1)) is None                        # not due yet
    row = c.tick(now + timedelta(minutes=5))
    assert row["action"] == "collected" and row["gap_min"] == 5.0
    assert sum(u.endswith("/odds") for u in odds.calls) == 2 and sum(u.endswith("/events") for u in odds.calls) == 1
    stored = list((tmp / "raw" / "nba" / "collector_oddsapi").rglob("*.parquet"))
    assert len(stored) == 2 and all(b"SECRET" not in p.read_bytes() for p in stored)
    assert len(list((tmp / "raw" / "nba" / "collector_kalshi").rglob("*.parquet"))) == 2
    assert json.loads((tmp / "quota.json").read_text())["project"] == "sharp-markets"


def test_idle_outside_the_window_spends_nothing(env):
    c, odds, kalshi, tmp = env
    now = TIP + timedelta(minutes=20)                                        # after tip + 15 min
    paid(tmp, now=now)
    assert c.tick(now)["action"] == "idle"
    assert not any(u.endswith("/odds") for u in odds.calls) and kalshi.calls == []
    assert [r["action"] for r in runs(tmp)] == ["idle"]


def test_free_plan_or_low_quota_skips_the_paid_call_but_keeps_kalshi(env, monkeypatch):
    c, odds, kalshi, tmp = env
    now = TIP - timedelta(hours=1)
    paid(tmp, remaining=450, used=50, now=now)                               # the free plan
    row = c.tick(now)
    assert row["odds_status"] == "skipped" and "paid plan" in row["note"] and row["kalshi_status"] == 200
    assert not any(u.endswith("/odds") for u in odds.calls)
    paid(tmp, remaining=99_000, used=4_901_000, now=now)                     # below 2% of 5M
    row = c.tick(now + timedelta(minutes=5))
    assert row["odds_status"] == "skipped" and "floor 100000" in row["note"]
    monkeypatch.setenv("ODDS_BACKGROUND_FLOOR", "1000")
    assert c.tick(now + timedelta(minutes=10))["odds_status"] == 200


def test_quota_records_carry_the_key_fingerprint_and_other_keys_are_ignored(env):
    """#33 item 2: the shared quota file says which key made the call (a fingerprint, never the key)."""
    c, odds, kalshi, tmp = env
    now = TIP - timedelta(hours=3)
    paid(tmp, now=now)                                                       # no fingerprint: still read
    assert c.tick(now)["odds_status"] == 200
    s = json.loads((tmp / "quota.json").read_text())
    assert s["key"] == col.fingerprint("SECRET") and "SECRET" not in (tmp / "quota.json").read_text()
    other = dict(s, key=col.fingerprint("ANOTHER"))
    (tmp / "quota.json").write_text(json.dumps(other))                       # a paid plan, but another key's
    row = c.tick(now + timedelta(minutes=5))
    assert row["odds_status"] == "skipped" and "paid plan" in row["note"]

def test_a_future_last_tick_counts_as_due(env):
    """#33 item 3: state from a --now run in the future must not stop real ticks until then."""
    c, odds, kalshi, tmp = env
    now = TIP - timedelta(hours=3)
    paid(tmp, now=now)
    (tmp / "collector" / "nba").mkdir(parents=True)
    (tmp / "collector" / "nba" / "state.json").write_text(json.dumps({"last_tick": "2026-12-25T00:00:00Z"}))
    assert c.tick(now)["action"] == "collected"


def test_dry_run_spends_nothing_and_writes_no_quota(tmp_path, monkeypatch):
    """#33 item 3: `collect --now` runs dry: Kalshi and the free schedule only, no paid call, no quota write."""
    monkeypatch.setattr(col, "QUOTA_FILE", tmp_path / "quota.json")
    odds, kalshi = FakeOdds(), FakeKalshi()
    c = col.Collector(cfg=dict(CFG), data_dir=tmp_path / "scratch", odds_session=odds, kalshi_session=kalshi,
                      api_key="SECRET", dry_run=True)
    c.kalshi.limiter = c.limiter
    row = c.tick(TIP - timedelta(hours=3))
    assert row["odds_status"] == "skipped" and "dry run" in row["note"] and row["kalshi_status"] == 200
    assert not any(u.endswith("/odds") for u in odds.calls) and not (tmp_path / "quota.json").exists()

def test_ticks_look_only_in_their_own_date_directory(env):
    """#33 item 12: a tick never lists the collector's whole raw history, only its own date's directory."""
    c, odds, kalshi, tmp = env
    now = TIP - timedelta(hours=3)
    paid(tmp, now=now)
    old = tmp / "raw" / "nba" / "collector_oddsapi" / "2026-10-20"
    old.mkdir(parents=True)
    (old / "0123456789abcdef0123.parquet").write_bytes(b"not read")
    assert c.tick(now)["odds_status"] == 200
    keys = set(c.cache._index)
    assert ("nba", "collector_oddsapi") not in keys and ("nba", "collector_kalshi") not in keys
    assert ("nba", "collector_oddsapi", now.date().isoformat()) in keys

def test_one_minute_ticks_in_the_final_window_when_enabled(env):
    c, odds, kalshi, tmp = env
    c.c["final_every_min"] = 1
    far = TIP - timedelta(hours=5)
    paid(tmp, now=far)
    assert c.tick(far)["final_window"] is False
    assert c.tick(far + timedelta(minutes=1)) is None                        # 5-minute ticks outside the final 2h
    now = TIP - timedelta(minutes=90)
    assert c.tick(now)["final_window"] is True
    assert c.tick(now + timedelta(minutes=1))["action"] == "collected"       # 1-minute ticks inside it


def test_lock_prevents_overlap_and_errors_are_logged(env):
    c, odds, kalshi, tmp = env
    now = TIP - timedelta(hours=1)
    paid(tmp, now=now)
    (tmp / "collector" / "nba").mkdir(parents=True)
    with (tmp / "collector" / "nba" / "tick.lock").open("a+") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert c.tick(now) is None
    # A dead owner releases the kernel lock; a stale inode alone never blocks.

    def boom(*a, **k):
        raise ConnectionError("down")
    kalshi.get = boom
    row = c.tick(now)
    assert row["kalshi_status"] == "error" and row["odds_status"] == 200    # one source failing keeps the other


def test_a_network_error_note_never_holds_the_key(tmp_path, monkeypatch):
    """The heartbeat keeps each error's text. requests puts the URL, key included, into its errors;
    markets.http blanks it before the error reaches the collector (audit 2, finding 1)."""
    import requests

    from markets import http
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    monkeypatch.setattr(col, "QUOTA_FILE", tmp_path / "quota.json")

    class Down:
        def get(self, url, params=None, timeout=None, allow_redirects=True):     # what requests raises when the host can't be reached
            raise requests.ConnectionError(f"HTTPSConnectionPool(host='odds.invalid', port=443): Max retries exceeded "
                                           f"with url: /v4{url.split('/v4')[1]}?dateFormat=iso&apiKey={params['apiKey']}")

    c = col.Collector(cfg=dict(CFG), data_dir=tmp_path, odds_session=Down(), kalshi_session=FakeKalshi(),
                      api_key="FAKESECRETKEY999")
    row = c.tick(TIP - timedelta(hours=3))
    assert row["action"] == "error" and "apiKey=REDACTED" in row["note"]
    stored = "".join(p.read_text() for p in (tmp_path / "collector").rglob("*") if p.is_file())
    assert "FAKESECRETKEY999" not in stored and "FAKESECRETKEY999" not in json.dumps(row)


def test_an_echoed_error_body_never_reaches_the_heartbeat(tmp_path, monkeypatch):
    """Audit 2 review: the schedule error kept the first 200 characters of the body, so a server or proxy that
    echoes the request would have written the key into runs.csv (the collector's log on the Mac)."""
    from markets import http
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    monkeypatch.setattr(col, "QUOTA_FILE", tmp_path / "quota.json")

    class Echo:
        def get(self, url, params=None, timeout=None, allow_redirects=True):
            return Resp(500, {"message": f"oops GET /v4/sports/basketball_nba/events?apiKey={params['apiKey']}",
                              "path": f"/moved/{params['apiKey']}"})

    c = col.Collector(cfg=dict(CFG), data_dir=tmp_path, odds_session=Echo(), kalshi_session=FakeKalshi(),
                      api_key="FAKESECRETKEY999")
    row = c.tick(TIP - timedelta(hours=3))
    assert row["action"] == "error" and "HTTP 500" in row["note"] and "REDACTED" in row["note"]
    stored = "".join(p.read_text() for p in (tmp_path / "collector").rglob("*") if p.is_file())
    assert "FAKESECRETKEY999" not in stored and "FAKESECRETKEY999" not in json.dumps(row)


def test_real_config_loads():
    c = col.load_collector_config("nba")
    assert c["start"] == date(2026, 10, 20) and c["series_ticker"] == "KXNBAGAME" and c["every_min"] == 5
    assert c["bookmakers"] == ["pinnacle", "lowvig", "betonlineag"] and not c["final_every_min"]
