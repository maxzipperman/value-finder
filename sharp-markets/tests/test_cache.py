import json

from markets.cache import Fetched, RawCache, read_record


def test_cache_first_and_secret_stripping(tmp_path):
    calls = []

    def fetch():
        calls.append(1)
        return Fetched(200, {"x-requests-last": "10"}, json.dumps({"ok": True}))

    c1 = RawCache(tmp_path)
    kw = dict(sport="nba", source="oddsapi_hist", data_date="2026-01-05", url="https://x/y",
              params={"date": "2026-01-05T00:00:00Z", "apiKey": "SECRET"}, fetch=fetch)
    rec = c1.get_or_fetch(**kw)
    assert rec["http_status"] == 200 and len(calls) == 1
    assert "SECRET" not in rec["params_json"] and "apiKey" not in rec["params_json"]
    # a new cache instance (a rerun on another day) finds the file and never calls fetch
    c2 = RawCache(tmp_path)
    rec2 = c2.get_or_fetch(**{**kw, "data_date": "2026-09-27"})
    assert len(calls) == 1 and c2.http_requests == 0 and json.loads(rec2["body"]) == {"ok": True}
    stored = list(tmp_path.rglob("*.parquet"))
    assert len(stored) == 1 and "SECRET" not in read_record(stored[0])["params_json"]


def test_errors_not_cached(tmp_path):
    c = RawCache(tmp_path)
    rec = c.get_or_fetch(sport="nba", source="s", data_date="d", url="u", params={},
                         fetch=lambda: Fetched(500, {}, "boom"), cache_statuses=(200,))
    assert rec["http_status"] == 500 and not list(tmp_path.rglob("*.parquet"))


def test_dated_sources_hit_in_their_date_directory_only(tmp_path):
    """#33 item 12: a dated source is looked up in data_date's directory only, and still hits there."""
    calls = []

    def fetch():
        calls.append(1)
        return Fetched(200, {}, "{}")
    kw = dict(sport="nba", source="collector_oddsapi", url="u", params={"a": 1}, fetch=fetch,
              key_extra={"tick": "2026-10-21T20:00:00Z"})
    RawCache(tmp_path, dated_sources=frozenset({"collector_oddsapi"})).get_or_fetch(data_date="2026-10-21", **kw)
    again = RawCache(tmp_path, dated_sources=frozenset({"collector_oddsapi"}))
    again.get_or_fetch(data_date="2026-10-21", **kw)
    assert calls == [1] and set(again._index) == {("nba", "collector_oddsapi", "2026-10-21")}
