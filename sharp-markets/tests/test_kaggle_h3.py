"""H3 on the Kaggle MGM splits: the credential path and the registered test, all offline.

Every test runs with a fake token in a fake home folder and a fake HTTP transport: nothing here touches the network
or the owner's real token (the autouse fixture checks that the token file it would read is inside tmp_path).
"""
import io
import json
import os
from urllib.parse import urlsplit

import pytest
import requests
from requests.adapters import HTTPAdapter
from requests.structures import CaseInsensitiveDict

from markets.research import kaggle_h3 as k

FAKE = "KGAT_fake0123456789abcdefFAKEFAKE"
SIGNED = "X-Goog-Signature=deadbeefSIGNED"
STORAGE = "storage.googleapis.com"
DL_PATH = f"/api/v1/datasets/download/{k.DATASET}"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".kaggle").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    for name in ("KAGGLE_API_TOKEN", "KAGGLE_USERNAME", "KAGGLE_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(k, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(k, "REPORTS_DIR", tmp_path / "reports")

    def no_network(self, request, **kw):
        raise AssertionError(f"unexpected network call to {urlsplit(request.url).hostname}")

    monkeypatch.setattr(HTTPAdapter, "send", no_network)
    assert str(k.token_file()).startswith(str(tmp_path))      # never the real ~/.kaggle/access_token
    return home


def _token_file(mode=0o600, text=FAKE + "\n"):
    p = k.token_file()
    p.write_text(text)
    os.chmod(p, mode)
    return p


def _zip(csv_text="a,b\n1,2\n"):
    buf = io.BytesIO()
    import zipfile
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("all_odds.csv", csv_text)
    return buf.getvalue()


class FakeHTTP:
    """Answers by (host, path); records every request's host, URL and headers. Unknown routes get `default` (if
    given) or fail the test. The host is read from the address as requests will connect to it."""

    def __init__(self, routes, default=None):
        self.routes, self.seen, self.default = routes, [], default

    def send(self, adapter, request, **kw):
        parts = urlsplit(request.url)
        self.seen.append({"host": parts.hostname, "url": request.url, "headers": dict(request.headers)})
        answer = self.routes.get((parts.hostname, parts.path), self.default)
        if answer is None:
            raise AssertionError(f"no fake route for {parts.hostname}")
        if isinstance(answer, Exception):
            raise answer
        status, body, headers = answer
        r = requests.Response()
        r.status_code, r._content, r._content_consumed = status, body, True
        r.raw, r.url, r.request, r.encoding, r.reason = io.BytesIO(body), request.url, request, "utf-8", "fake"
        r.headers = CaseInsensitiveDict(headers or {})
        return r


def _install(monkeypatch, routes, default=None):
    fake = FakeHTTP(routes, default)
    monkeypatch.setattr(HTTPAdapter, "send", lambda self, request, **kw: fake.send(self, request, **kw))
    return fake


def _redirecting_download(blob):
    return {("www.kaggle.com", DL_PATH): (302, b"", {"Location": f"https://{STORAGE}/bucket/archive.zip?{SIGNED}"}),
            (STORAGE, "/bucket/archive.zip"): (200, blob, {"Content-Type": "application/zip"})}


def _all_text_under(path):
    return "\n".join(p.read_bytes().decode("latin-1") for p in path.rglob("*") if p.is_file())


# ---------------------------------------------------------------- credential and download

def test_bearer_goes_to_kaggle_and_not_to_the_redirect_host(monkeypatch, tmp_path):
    _token_file()
    blob = _zip()
    fake = _install(monkeypatch, _redirecting_download(blob))
    assert k.download() == blob
    assert [s["host"] for s in fake.seen] == ["www.kaggle.com", STORAGE]
    assert fake.seen[0]["headers"]["Authorization"] == f"Bearer {FAKE}"
    storage_headers = fake.seen[1]["headers"]
    assert "Authorization" not in storage_headers
    assert not any(FAKE in str(v) for v in storage_headers.values())
    rec = json.loads(next((tmp_path / "raw").rglob("download.json")).read_text())
    assert set(rec) == {"dataset", "downloaded_utc", "bytes", "sha256"}
    assert rec["dataset"] == k.DATASET and rec["bytes"] == len(blob)
    import hashlib
    assert rec["sha256"] == hashlib.sha256(blob).hexdigest()
    saved = _all_text_under(tmp_path / "raw")
    assert FAKE not in saved and "SIGNED" not in saved and STORAGE not in saved


def test_requests_itself_drops_the_header_on_a_cross_host_redirect(monkeypatch):
    """The belt under the braces: even requests' own redirect handling strips Authorization for another host."""
    fake = _install(monkeypatch, _redirecting_download(_zip()))
    requests.Session().get(f"https://www.kaggle.com{DL_PATH}", headers={"Authorization": f"Bearer {FAKE}"})
    assert fake.seen[0]["headers"]["Authorization"] == f"Bearer {FAKE}"
    assert fake.seen[1]["host"] == STORAGE and "Authorization" not in fake.seen[1]["headers"]


# Redirect addresses a hostile or broken server could send. The first one is the review's case: Python's urlsplit
# reads its host as www.kaggle.com, but requests connects to evil.example.
HOSTILE_LOCATIONS = [
    "https://evil.example\\@www.kaggle.com/x",
    "https://evil.example%5C@www.kaggle.com/x",
    "https://www.kaggle.com@evil.example/x",
    "https://evil.example#@www.kaggle.com/x",
    "https://evil.example?@www.kaggle.com/x",
    "https://evil.example/ @www.kaggle.com/x",
    "https://evil.example\t@www.kaggle.com/x",
    "//evil.example/x",
    "https://www.kaggle.com./x",
    "https://www.kaggle.com:8443/x",
    "https://www.kaggle.com/api/v1/somewhere-else",       # not even Kaggle itself gets the credential on a redirect
]


@pytest.mark.parametrize("location", HOSTILE_LOCATIONS)
def test_no_redirect_hop_carries_the_credential(monkeypatch, capsys, location):
    _token_file()
    fake = _install(monkeypatch, {("www.kaggle.com", DL_PATH): (302, b"", {"Location": location})},
                    default=(404, b"", {}))
    with pytest.raises(SystemExit) as e:
        k.download()
    assert fake.seen[0]["host"] == "www.kaggle.com" and fake.seen[0]["headers"]["Authorization"] == f"Bearer {FAKE}"
    for later in fake.seen[1:]:
        assert "Authorization" not in later["headers"], later["host"]
        assert not any(FAKE in str(v) for v in later["headers"].values())
    text = str(e.value)
    assert FAKE not in text and "\n" not in text and e.value.__context__ is None
    out = capsys.readouterr()
    assert FAKE not in out.out + out.err


def test_the_backslash_redirect_is_refused_before_any_request_to_it(monkeypatch):
    _token_file()
    fake = _install(monkeypatch, {("www.kaggle.com", DL_PATH):
                                  (302, b"", {"Location": "https://evil.example\\@www.kaggle.com/x"})})
    with pytest.raises(SystemExit) as e:
        k.download()
    assert "refused" in str(e.value)
    assert [s["host"] for s in fake.seen] == ["www.kaggle.com"]


@pytest.mark.parametrize("url", ["https://evil.example/api/v1/x", "http://www.kaggle.com/api/v1/x",
                                 "https://evil.example\\@www.kaggle.com/api/v1/x",
                                 "https://www.kaggle.com@evil.example/api/v1/x",
                                 "https://www.kaggle.com:8443/api/v1/x"])
def test_the_credential_is_only_ever_attached_for_the_kaggle_api_address(monkeypatch, url):
    _token_file()
    fake = _install(monkeypatch, {}, default=(200, b"{}", {}))
    with pytest.raises(SystemExit) as e:
        k._get(url, k._credential(), "test")
    assert FAKE not in str(e.value)
    assert fake.seen == []


def test_a_dataset_name_from_search_results_cannot_change_the_host(monkeypatch):
    """dataset_files() takes names that come back from Kaggle's search; they are escaped into the path."""
    _token_file()
    fake = _install(monkeypatch, {}, default=(404, b"", {}))
    with pytest.raises(SystemExit):
        k.dataset_files("evil.example\\@x/y@evil.example")
    assert [s["host"] for s in fake.seen] == ["www.kaggle.com"]
    assert "%5C" in fake.seen[0]["url"] and "%40" in fake.seen[0]["url"]


def test_group_readable_token_file_is_refused_before_any_request(monkeypatch, capsys):
    _token_file(mode=0o640)
    fake = _install(monkeypatch, _redirecting_download(_zip()))
    with pytest.raises(SystemExit) as e:
        k.download()
    assert "chmod 600" in str(e.value) and FAKE not in str(e.value)
    assert fake.seen == []
    out = capsys.readouterr()
    assert FAKE not in out.out + out.err


def test_token_with_a_line_break_inside_is_not_sent(monkeypatch):
    _token_file(text=FAKE[:10] + "\n" + FAKE[10:])
    fake = _install(monkeypatch, _redirecting_download(_zip()))
    with pytest.raises(SystemExit) as e:
        k.download()
    assert FAKE[:10] not in str(e.value) and FAKE[10:] not in str(e.value)
    assert fake.seen == []


def test_environment_token_comes_first_then_file_then_basic(monkeypatch):
    _token_file()
    monkeypatch.setenv("KAGGLE_API_TOKEN", "KGAT_fromenvironment")
    fake = _install(monkeypatch, _redirecting_download(_zip()))
    k.download()
    assert fake.seen[0]["headers"]["Authorization"] == "Bearer KGAT_fromenvironment"

    # basic auth only when there is no token at all, and still only to www.kaggle.com
    monkeypatch.delenv("KAGGLE_API_TOKEN")
    k.token_file().unlink()
    monkeypatch.setenv("KAGGLE_USERNAME", "someone")
    monkeypatch.setenv("KAGGLE_KEY", "fakekey123")
    fake = _install(monkeypatch, _redirecting_download(_zip()))
    k.download(force=True)
    assert fake.seen[0]["headers"]["Authorization"].startswith("Basic ")
    assert "Authorization" not in fake.seen[1]["headers"]


def test_no_credential_at_all_is_one_plain_line(monkeypatch):
    fake = _install(monkeypatch, _redirecting_download(_zip()))
    with pytest.raises(SystemExit) as e:
        k.download()
    assert "No Kaggle credential" in str(e.value) and fake.seen == []


@pytest.mark.parametrize("routes, expect", [
    ({("www.kaggle.com", DL_PATH): (401, json.dumps({"code": 401, "message": f"Bearer {FAKE} is not valid"}).encode(),
                                    {"Content-Type": "application/json"})}, "HTTP 401 from www.kaggle.com"),
    ({("www.kaggle.com", DL_PATH): (403, json.dumps({"message": f"token {FAKE} forbidden"}).encode(), {})},
     "HTTP 403 from www.kaggle.com"),
    ({("www.kaggle.com", DL_PATH): (302, b"", {"Location": f"https://{STORAGE}/bucket/archive.zip?{SIGNED}"}),
      (STORAGE, "/bucket/archive.zip"): (403, f"<Error>{SIGNED} {FAKE}</Error>".encode(), {})},
     f"HTTP 403 from {STORAGE}"),
    ({("www.kaggle.com", DL_PATH): requests.ConnectionError(f"https://www.kaggle.com/?t={FAKE}&{SIGNED}")},
     "no usable response from www.kaggle.com (ConnectionError)"),
    ({("www.kaggle.com", DL_PATH): (302, b"", {"Location": f"http://{STORAGE}/bucket/archive.zip?{SIGNED}"})},
     "non-https"),
    ({("www.kaggle.com", DL_PATH): (200, b"<html>not a zip</html>", {"Content-Type": "text/html"})},
     "is not a zip file"),
])
def test_failures_print_one_plain_line_without_the_token(monkeypatch, capsys, tmp_path, routes, expect):
    _token_file()
    fake = _install(monkeypatch, routes)
    with pytest.raises(SystemExit) as e:
        k.download()
    text = str(e.value)
    assert expect in text
    assert "\n" not in text
    assert FAKE not in text and "SIGNED" not in text
    assert e.value.__cause__ is None and e.value.__context__ is None
    out = capsys.readouterr()
    assert FAKE not in out.out + out.err
    assert all(s["host"] == "www.kaggle.com" or "Authorization" not in s["headers"] for s in fake.seen)
    raw = tmp_path / "raw"
    assert not raw.exists() or (FAKE not in _all_text_under(raw) and "SIGNED" not in _all_text_under(raw))


def test_kaggle_message_is_kept_but_the_token_is_removed(monkeypatch):
    _token_file()
    body = json.dumps({"message": f"Unauthenticated: Bearer {FAKE} expired; token={FAKE}"}).encode()
    _install(monkeypatch, {("www.kaggle.com", DL_PATH): (401, body, {})})
    with pytest.raises(SystemExit) as e:
        k.download()
    assert "Unauthenticated" in str(e.value) and "[removed]" in str(e.value) and FAKE not in str(e.value)


def test_the_cache_is_used_on_a_rerun(monkeypatch):
    _token_file()
    blob = _zip()
    fake = _install(monkeypatch, _redirecting_download(blob))
    k.download()
    assert len(fake.seen) == 2
    monkeypatch.setattr(HTTPAdapter, "send", lambda self, request, **kw: pytest.fail("network on a cached rerun"))
    assert k.download() == blob
    assert k.download_record()["bytes"] == len(blob)


def test_search_and_file_list_are_read_only_and_cached(monkeypatch, tmp_path):
    _token_file()
    listing = [{"ref": "someone/nfl-splits", "title": "NFL splits"}]
    files = {"datasetFiles": [{"name": "splits.csv", "totalBytes": 10, "columns": [{"name": "bets_pct"}]}]}
    fake = _install(monkeypatch, {("www.kaggle.com", "/api/v1/datasets/list"): (200, json.dumps(listing).encode(), {}),
                                  ("www.kaggle.com", "/api/v1/datasets/list/someone/nfl-splits"):
                                      (200, json.dumps(files).encode(), {})})
    assert k.search("betting splits") == listing
    assert k.dataset_files("someone/nfl-splits") == files
    assert [s["headers"]["Authorization"] for s in fake.seen] == [f"Bearer {FAKE}"] * 2
    assert "search=betting+splits" in fake.seen[0]["url"]
    monkeypatch.setattr(HTTPAdapter, "send", lambda self, request, **kw: pytest.fail("network on a cached rerun"))
    assert k.search("betting splits") == listing and k.dataset_files("someone/nfl-splits") == files
    assert FAKE not in _all_text_under(tmp_path / "raw")


# ---------------------------------------------------------------- the registered test on a hand-built file

# Each market: (price side 1, price side 2, money share side 1, ticket share side 1, side 1 won). Side 2's shares are
# 100 minus side 1's. won: 1, 0, "push" (both sides lose) or "both" (both marked won). None = a blank figure.
GAMES = [
    # id    date          home                    away                     moneyline                   spread                        total (over first)
    ("G1", "2021-11-01", "Boston Celtics", "Miami Heat", (1.5, 2.8, 80, 60, 1), (1.8, 2.0, 70, 55, 1), (1.91, 1.91, 60, 70, 1)),
    ("G2", "2021-11-01", "Chicago Bulls", "Utah Jazz", (2.5, 1.6, 30, 40, 0), (1.91, 1.91, 40, 52, 1), (1.87, 1.95, 75, 60, 0)),
    ("G3", "2022-12-01", "Denver Nuggets", "LA Clippers", (1.25, 4.2, 85, 90, 1), (1.91, 1.91, 55, 50, 0), (1.91, 1.91, 50, 25, 1)),
    ("G4", "2023-12-01", "Phoenix Suns", "New York",(1.91, 1.91, 50, 50, 0), (1.91, 1.91, 50, 50, 1), (1.91, 1.91, 35, 50, 0)),
    ("G5", "2024-12-01", "Golden State Warriors", "Dallas Mavericks", (1.4, 3.1, 60, 70, 0), (1.91, 1.91, 30, 20, 1), (1.91, 1.91, 50, 50, "push")),
    ("G6", "2025-12-01", "Toronto Raptors", "Detroit Pistons", (3.0, 1.4, 20, 35, 1), (1.91, 1.91, 45, 75, 1), (1.95, 1.87, 70, 65, 1)),
    ("G7", "2026-01-31", "Sacramento Kings", "Houston Rockets", (1.7, 2.2, 57, 50, 1), (1.91, 1.91, 62, 50, 0), (1.91, 1.91, 40, 72, 1)),
    ("G8", "2026-02-01", "Boston Celtics", "Miami Heat", (1.1, 9.0, 99, 1, "both"), (1.91, 1.91, 90, 10, "both"), (1.91, 1.91, 90, 10, "both")),
    ("G9", "2023-12-02", "Atlanta Hawks", "Brooklyn Nets", (1.91, 1.91, 50, 50, 1), (1.91, 1.91, 80, 40, "push"), (1.91, 1.91, 55, 45, 0)),
    ("G10", "2024-12-02", "Memphis Grizzlies", "New York Knicks", (1.91, 1.91, 55, 50, 0), (1.91, 1.91, None, 50, 1), (1.91, 1.91, 50, 50, 1)),
    ("G11", "2022-12-02", "Indiana Pacers", "Charlotte Hornets", (1.8, 2.05, 45, 50, 1), (1.91, 1.91, 50, 50, 1), (1.5, 1.5, 90, 10, 1)),
]


def _csv_text(games=GAMES, drop=()):
    cols = ["game_id", "game_date", "home_team", "away_team"]
    for m in k.MARKETS:
        for s in k.SIDES[m]:
            cols += [f"{m}_{s}_{f}" for f in ("decimal_odds", "stake_percentage", "wager_percentage", "won", "points")]
    cols = [c for c in cols if c not in drop]
    buf = io.StringIO()
    w = __import__("csv").DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for gid, d, home, away, *mk in games:
        row = {"game_id": gid, "game_date": f"{d}-10:00", "home_team": home, "away_team": away}   # the file's format
        for m, (p1, p2, st1, wg1, won1) in zip(k.MARKETS, mk):
            s1, s2 = k.SIDES[m]
            w1, w2 = {1: ("True", "False"), 0: ("False", "True"), "push": ("False", "False"),
                      "both": ("True", "True")}[won1]
            line = {"money": ("", ""), "spread": ("-3.5", "3.5"), "total": ("220.5", "220.5")}[m]
            for s, p, st, wg, won, ln in ((s1, p1, st1, wg1, w1, line[0]),
                                          (s2, p2, None if st1 is None else 100 - st1, 100 - wg1, w2, line[1])):
                row |= {f"{m}_{s}_decimal_odds": p, f"{m}_{s}_stake_percentage": "" if st is None else st,
                        f"{m}_{s}_wager_percentage": wg, f"{m}_{s}_won": won, f"{m}_{s}_points": ln}
        w.writerow(row)
    return buf.getvalue()


def _analysed():
    from markets.sport import load_teams
    rows, fields = k.load_rows(_zip(_csv_text()))
    games, info = k.parse_games(rows, load_teams("nba"))
    return games, info, k.analyse(games)


def _v(res, family, market, kpts=None):
    return next(v for v in res["variants"] if v["family"] == family and v["market"] == market
                and (kpts is None or v["k"] == kpts))


def _fair(a, b):
    return (1 / a) / (1 / a + 1 / b)


def _expected_mean_test(r, dates, fairs, won, decs):
    """Our own arithmetic for families A and C: plain and grouped standard errors, the wider, t on its df."""
    import numpy as np
    from scipy import stats
    r, n = np.array(r, float), len(r)
    m = r.mean()
    se_plain = r.std(ddof=1) / np.sqrt(n)
    by = {}
    for d, x in zip(dates, r):
        by[d] = by.get(d, 0.0) + (x - m)
    G = len(by)
    se_grouped = np.sqrt(G / (G - 1) * sum(v ** 2 for v in by.values()) / n ** 2)
    se, df = (se_plain, n - 1) if se_plain > se_grouped else (se_grouped, G - 1)
    return {"n": n, "est": m, "se_plain": se_plain, "se_grouped": se_grouped, "G": G, "se": se,
            "p": 2 * stats.t.sf(abs(m) / se, df), "win_rate": np.mean(won), "mean_fair": np.mean(fairs),
            "roi": np.mean([(d - 1) if w else -1 for d, w in zip(decs, won)]),
            "detectable": stats.norm.isf(0.05 / 287 / 2) * 0.5 / np.sqrt(n)}


def _check(v, want):
    for key, val in want.items():
        assert v[key] == pytest.approx(val, rel=1e-9, abs=1e-12), key


def test_registration_constants():
    assert k.N_VARIANTS == 14 and k.PRIOR_COUNT == 273 and k.RUNNING_COUNT == 287
    assert k.BAR == pytest.approx(0.05 / 287) and round(k.BAR, 6) == 0.000174
    assert k.Z_BAR == pytest.approx(3.7537, abs=1e-4)
    assert k.CUTOFF.isoformat() == "2026-01-31" and k.THRESHOLDS == (5, 10, 15) and k.FADE_MAX_TICKETS == 30
    reg = (k.Path(k.__file__).resolve().parents[3] / "docs" / "H3_KAGGLE_PREREGISTRATION.md").read_text()
    for phrase in ("14 variants", "273 to 287", "0.000174", "January 31, 2026", "at least 4 of the 5 seasons",
                   "30% of the tickets or fewer", "k of 5, 10 and 15"):
        assert phrase in reg, phrase


def test_cutoff_pushes_and_missing_figures():
    games, info, res = _analysed()
    assert res["n_variants"] == 14 and len(res["variants"]) == 14
    assert info["n_rows"] == 11 and info["after_cutoff"] == 1 and len(games) == 10
    assert "G8" not in {g["key"] for g in games}
    assert "G7" in {g["key"] for g in games}                       # the cut-off day itself is in
    assert res["excluded"]["money"] == {}
    assert res["excluded"]["spread"] == {"push": 1, "missing figure": 1}          # G9, G10
    assert res["excluded"]["total"] == {"push": 1, "margin below 0% or above 20%": 1}   # G5, G11
    assert res["n_records"] == {"money": 10, "spread": 8, "total": 8}
    # an unresolved team name is counted, and the game stays in the test (team names play no part in it)
    assert info["unknown_teams"] == {"New York": 1}
    g4 = next(g for g in games if g["key"] == "G4")
    assert g4["away"] is None and g4["home"] == "PHX"


def test_the_files_date_format():
    assert k._date("2021-10-19-10:00").isoformat() == "2021-10-19"
    assert k._date("2026-01-31-10:00") == k.CUTOFF
    assert k._date("2026-02-01-10:00") > k.CUTOFF
    assert k._date("2021-10-19") .isoformat() == "2021-10-19"
    assert k._date("") is None and k._date("2021-13-40-10:00") is None and k._date("garbage") is None
    assert k.season_of(k._date("2022-08-01-10:00")) == "2022-23" and k.season_of(k._date("2022-07-31")) == "2021-22"


def test_family_a_spread_by_hand():
    """Spread, money share minus ticket share >= 5: G1 home (+15), G2 away (+12), G3 home (+5), G5 home (+10),
    G6 away (+30), G7 home (+12). G4 (0) and G11 (0) don't qualify; G9 is a push and G10 has a blank."""
    _, _, res = _analysed()
    f1 = _fair(1.8, 2.0)                                           # 0.526316: G1's home side at 1.80 / 2.00
    r = [1 - f1, 0 - 0.5, 0 - 0.5, 1 - 0.5, 0 - 0.5, 0 - 0.5]
    dates = ["2021-11-01", "2021-11-01", "2022-12-01", "2024-12-01", "2025-12-01", "2026-01-31"]
    want = _expected_mean_test(r, dates, [f1, .5, .5, .5, .5, .5], [1, 0, 0, 1, 0, 0], [1.8, 1.91, 1.91, 1.91, 1.91, 1.91])
    v = _v(res, "A", "spread", 5)
    _check(v, {x: want[x] for x in ("n", "est", "se_plain", "se_grouped", "G", "se", "p", "win_rate", "mean_fair",
                                    "roi", "detectable")})
    assert v["est"] == pytest.approx((1 - f1 - 4 * 0.5 + 0.5) / 6)   # -0.171053
    assert v["roi"] == pytest.approx((0.8 - 1 - 1 + 0.91 - 1 - 1) / 6)
    # seasons: 2021-22 (G1, G2) mean (0.4737 - 0.5) / 2 < 0; 2022-23 -0.5; 2023-24 none; 2024-25 +0.5; 2025-26 -0.5
    assert v["signs"] == {"2021-22": -1, "2022-23": -1, "2023-24": None, "2024-25": 1, "2025-26": -1}
    assert v["same_sign"] == 3 and not v["passes"]

    v10 = _v(res, "A", "spread", 10)                               # G3 (+5) drops out
    want = _expected_mean_test([1 - f1, -0.5, 0.5, -0.5, -0.5], dates[:2] + dates[3:], [f1, .5, .5, .5, .5],
                               [1, 0, 1, 0, 0], [1.8, 1.91, 1.91, 1.91, 1.91])
    _check(v10, {x: want[x] for x in ("n", "est", "se_plain", "se_grouped", "se", "p", "roi")})
    v15 = _v(res, "A", "spread", 15)                               # G1 (+15) and G6 (+30)
    want = _expected_mean_test([1 - f1, -0.5], ["2021-11-01", "2025-12-01"], [f1, .5], [1, 0], [1.8, 1.91])
    _check(v15, {x: want[x] for x in ("n", "est", "se_plain", "se_grouped", "se", "p", "roi")})


def test_family_a_moneyline_and_total_by_hand():
    _, _, res = _analysed()
    # moneyline divergences (home): G1 +20, G2 -10, G3 -5, G4 0, G5 -10, G6 -15, G7 +7, G9 0, G10 +5, G11 -5
    ml = {  # game: (side backed at k=5, its fair chance, won, its price, date)
        "G1": (_fair(1.5, 2.8), 1, 1.5, "2021-11-01"), "G2": (_fair(1.6, 2.5), 1, 1.6, "2021-11-01"),
        "G3": (_fair(4.2, 1.25), 0, 4.2, "2022-12-01"), "G5": (_fair(3.1, 1.4), 1, 3.1, "2024-12-01"),
        "G6": (_fair(1.4, 3.0), 0, 1.4, "2025-12-01"), "G7": (_fair(1.7, 2.2), 1, 1.7, "2026-01-31"),
        "G10": (0.5, 0, 1.91, "2024-12-02"), "G11": (_fair(2.05, 1.8), 0, 2.05, "2022-12-02")}
    for kpts, games in ((5, ["G1", "G2", "G3", "G5", "G6", "G7", "G10", "G11"]), (10, ["G1", "G2", "G5", "G6"]),
                        (15, ["G1", "G6"])):
        rows = [ml[g] for g in games]
        want = _expected_mean_test([w - f for f, w, _, _ in rows], [d for *_, d in rows], [f for f, *_ in rows],
                                   [w for _, w, _, _ in rows], [p for _, _, p, _ in rows])
        _check(_v(res, "A", "money", kpts), {x: want[x] for x in ("n", "est", "se_plain", "se_grouped", "se", "p",
                                                                   "win_rate", "mean_fair", "roi", "detectable")})
    # totals (over first): G1 under +10 (over won), G2 over +15, G3 over +25, G4 under +15, G6 over +5,
    # G7 under +32 (over won), G9 over +10; G5 push and G11 bad margin are out; G10 is 0
    tot = {"G1": (0.5, 0, 1.91, "2021-11-01"), "G2": (_fair(1.87, 1.95), 0, 1.87, "2021-11-01"),
           "G3": (0.5, 1, 1.91, "2022-12-01"), "G4": (0.5, 1, 1.91, "2023-12-01"),
           "G6": (_fair(1.95, 1.87), 1, 1.95, "2025-12-01"), "G7": (0.5, 0, 1.91, "2026-01-31"),
           "G9": (0.5, 0, 1.91, "2023-12-02")}
    for kpts, games in ((5, list(tot)), (10, ["G1", "G2", "G3", "G4", "G7", "G9"]), (15, ["G2", "G3", "G4", "G7"])):
        rows = [tot[g] for g in games]
        want = _expected_mean_test([w - f for f, w, _, _ in rows], [d for *_, d in rows], [f for f, *_ in rows],
                                   [w for _, w, _, _ in rows], [p for _, _, p, _ in rows])
        _check(_v(res, "A", "total", kpts), {x: want[x] for x in ("n", "est", "se_plain", "se_grouped", "se", "p",
                                                                   "win_rate", "mean_fair", "roi")})


def test_family_c_by_hand():
    _, _, res = _analysed()
    # spread: G5 home (20% of tickets) won; G6 away (25%) lost. G9's home would qualify on neither rule side
    v = _v(res, "C", "spread")
    assert v["n"] == 2 and v["est"] == pytest.approx(0.0) and v["win_rate"] == pytest.approx(0.5)
    assert v["roi"] == pytest.approx((0.91 - 1) / 2)
    # total: G1 under (exactly 30% of the tickets: "30% or fewer" includes it) lost; G3 over (25%) won; G7 under
    # (28%) lost; G11's under (10%) is out on its margin
    v = _v(res, "C", "total")
    assert v["n"] == 3 and v["est"] == pytest.approx(-1 / 6) and v["mean_fair"] == pytest.approx(0.5)
    want = _expected_mean_test([-0.5, 0.5, -0.5], ["2021-11-01", "2022-12-01", "2026-01-31"], [.5, .5, .5],
                               [0, 1, 0], [1.91, 1.91, 1.91])
    _check(v, {x: want[x] for x in ("se_plain", "se_grouped", "se", "p", "roi", "detectable", "win_rate")})
    assert v["signs"] == {"2021-22": -1, "2022-23": 1, "2023-24": None, "2024-25": None, "2025-26": -1}
    assert v["same_sign"] == 2 and not v["passes"]


def test_family_b_matches_statsmodels():
    import numpy as np
    import statsmodels.api as sm
    from scipy import stats
    games, _, res = _analysed()
    for m, s1 in (("money", "home"), ("spread", "home"), ("total", "over")):
        recs, _ = k.market_records(games, m)
        y = np.array([r["sides"][s1]["won"] - r["sides"][s1]["fair"] for r in recs])
        x = np.array([r["sides"][s1]["div"] / 10 for r in recs])
        tenth = np.array([min(int(r["sides"][s1]["fair"] * 10), 9) for r in recs])
        dates = np.array([r["date"].toordinal() for r in recs])
        present = sorted(set(tenth))
        X = np.column_stack([np.ones(len(y)), x] + [(tenth == q).astype(float) for q in present[1:]])
        hc1 = sm.OLS(y, X).fit(cov_type="HC1")
        cl = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": dates})
        v = _v(res, "B", m)
        assert v["n"] == len(y) and v["est"] == pytest.approx(hc1.params[1])
        assert v["se_plain"] == pytest.approx(hc1.bse[1]) and v["se_grouped"] == pytest.approx(cl.bse[1])
        wider_hc1 = hc1.bse[1] > cl.bse[1]
        df = len(y) - X.shape[1] if wider_hc1 else len(set(dates)) - 1
        assert v["p"] == pytest.approx(2 * stats.t.sf(abs(v["est"]) / max(hc1.bse[1], cl.bse[1]), df))
        assert v["wider"] == ("plain" if wider_hc1 else "grouped")
        assert v["detectable"] == pytest.approx(k.Z_BAR * 0.5 / (np.sqrt(len(y)) * x.std(ddof=1)))
    # the moneyline's home divergences, per 10 points, in game order (G8 is past the cut-off)
    recs, _ = k.market_records(games, "money")
    assert [r["sides"]["home"]["div"] for r in recs] == [20, -10, -5, 0, -10, -15, 7, 0, 5, -5]


def test_the_bar_needs_both_the_p_value_and_four_seasons():
    base = {"est": 0.05, "season": {s: (0.01, 10) for s in k.SEASONS}}
    assert k._sign_check(base | {"p": k.BAR / 2})["passes"]
    three = {s: (0.01 if i < 3 else -0.01, 10) for i, s in enumerate(k.SEASONS)}
    assert not k._sign_check(base | {"p": k.BAR / 2, "season": three})["passes"]
    four_and_empty = {s: ((0.01, 10) if i < 4 else (None, 0)) for i, s in enumerate(k.SEASONS)}
    assert k._sign_check(base | {"p": k.BAR / 2, "season": four_and_empty})["passes"]
    assert not k._sign_check(base | {"p": k.BAR * 1.01})["passes"]
    assert not k._sign_check(base | {"p": float("nan")})["passes"]


def test_a_season_figure_that_is_zero_up_to_rounding_has_no_sign():
    """The registration: a figure of exactly zero does not count as the same sign. The real file's family A total
    >= 15, 2023-24, came out as -1.85e-17 (six wins and six losses at even fair chances): that is zero."""
    seasons = {s: (-0.01, 10) for s in k.SEASONS} | {"2023-24": (-1.850371707708594e-17, 12)}
    r = k._sign_check({"est": -0.01, "p": k.BAR / 2, "season": seasons})
    assert r["signs"]["2023-24"] == 0 and r["same_sign"] == 4 and r["passes"]
    assert k._signs(r) == "− − 0 − −"
    r = k._sign_check({"est": -0.01, "p": k.BAR / 2, "season": seasons | {"2025-26": (None, 0)}})
    assert r["signs"]["2025-26"] is None and r["same_sign"] == 3 and not r["passes"]
    assert k._signs(r) == "− − 0 − ·"
    assert k._pts(-1.850371707708594e-17) == "0.00" and k._pts(-0.0001) == "-0.01"
    # an overall figure of zero has no sign, so no season can share it
    r = k._sign_check({"est": 1e-17, "p": k.BAR / 2, "season": {s: (0.01, 10) for s in k.SEASONS}})
    assert r["same_sign"] == 0 and not r["passes"]


def test_file_checks_count_exact_duplicates_and_rows_after_the_cutoff():
    from markets.sport import load_teams
    rows, _ = k.load_rows(_zip(_csv_text(GAMES + [GAMES[0]])))
    games, info = k.parse_games(rows, load_teams("nba"))
    ch = k.file_checks(games, info)
    assert info["exact_duplicate_rows"] == 1 and ch["dup_games"] == 1 and ch["dup_ids"] == 1
    assert info["after_cutoff"] == 1 and info["after_cutoff_by_season"] == {"2025-26": 1}
    assert ch["per_season"]["2025-26"]["after_cutoff"] == 1 and ch["per_season"]["2024-25"]["missing_splits"] == 1
    assert ch["markets"]["spread"]["counts"]["push"] == 1 and ch["markets"]["total"]["counts"]["push"] == 1
    assert ch["markets"]["spread"]["counts"]["whole-number line"] == 0            # every synthetic spread is 3.5
    assert info["constant_columns"]["spread_home_points"] == "-3.5"


def test_blank_results_on_whole_number_lines_and_price_mismatches_are_described_from_the_file():
    """A blank spread result on a whole-number line is probably a push the file left blank: the report says so from
    the file's own figures, with no outside push rates. The price check reports the largest mismatch."""
    import csv as _csv
    from markets.sport import load_teams
    rows = list(_csv.DictReader(io.StringIO(_csv_text())))
    for r in rows:
        r["money_home_odds"], r["money_away_odds"] = "", ""
        if r["game_id"] == "G2":                                   # the blank result, on a whole-number spread
            r |= {"spread_home_points": "-3", "spread_away_points": "3", "spread_home_won": "", "spread_away_won": ""}
        if r["game_id"] == "G1":                                   # 1.50 is -200 exactly; 2.80 is +180 exactly
            r |= {"money_home_odds": "-200", "money_away_odds": "180"}
        if r["game_id"] == "G3":                                   # -350 is 1.2857, given as 1.25: off by 0.0357
            r |= {"money_home_odds": "-350", "money_away_odds": "320"}
    buf = io.StringIO()
    w = _csv.DictWriter(buf, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
    edited, _ = k.load_rows(_zip(buf.getvalue()))
    games, info = k.parse_games(edited, load_teams("nba"))
    ch = k.file_checks(games, info)
    sp = ch["markets"]["spread"]
    assert sp["counts"]["missing result"] == 1 and sp["counts"]["whole-number line"] == 1
    assert sp["blank_result_whole_lines"] == [-3.0]
    line = k._pushes_line(ch)
    assert "1 spread has a blank result" in line and "−3" in line and "probably" in line
    assert "%" not in line and "usual" not in line                  # no push rates from outside the file
    mo = ch["markets"]["money"]
    assert mo["counts"]["prices checked against American odds"] == 4
    assert mo["counts"]["decimal and American differ by more than 0.01"] == 1
    assert mo["max_price_diff"] == pytest.approx(1 + 100 / 350 - 1.25)


def test_a_file_without_the_share_columns_stops(tmp_path):
    drop = tuple(f"{m}_{s}_stake_percentage" for m in k.MARKETS for s in k.SIDES[m])
    with pytest.raises(SystemExit) as e:
        k.run_h3(blob=_zip(_csv_text(drop=drop)), db_path=tmp_path / "db.duckdb", reports_dir=tmp_path / "rep")
    assert "not what PLAN.md describes" in str(e.value)
    assert not (tmp_path / "rep").exists()


def test_end_to_end_report_splits_table_and_no_token(monkeypatch, tmp_path, capsys):
    import duckdb
    _token_file()
    _install(monkeypatch, _redirecting_download(_zip(_csv_text())))
    db = tmp_path / "db.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE games (sport VARCHAR, game_id VARCHAR, game_date_et DATE, away_code VARCHAR, "
                "home_code VARCHAR)")
    con.execute("INSERT INTO games VALUES ('nba', 'KXNBAGAME-26JAN31HOUSAC', DATE '2026-01-31', 'HOU', 'SAC'), "
                "('nba', 'KXNBAGAME-26FEB01MIABOS', DATE '2026-02-01', 'MIA', 'BOS')")
    con.close()
    res = k.run_h3(db_path=db, reports_dir=tmp_path / "rep")
    assert res["n_variants"] == 14 and res["kalshi_joined_games"] == 1   # G7 joins; G8 is past the cut-off
    con = duckdb.connect(str(db))
    assert con.execute("SELECT count(DISTINCT source_game_key), count(*) FROM splits").fetchone() == (10, 60)
    assert con.execute("SELECT count(*) FROM splits WHERE game_date > DATE '2026-01-31'").fetchone()[0] == 0
    con.close()
    text = res["report"].read_text()
    assert "n_variants_tested = 14" in text and "0.000174" in text and "273 to 287" in text
    assert "None of the 14 variants passes the bar" in text and "recorded as a null" in text
    assert k.REGISTRATION["commit"] in text and res["sha256"] in text
    assert k.REGISTRATION["github_utc"] in text and k.REGISTRATION["code_github_utc"] in text
    assert "never read" not in text and "No result after the cut-off was computed" in text
    assert "the database this run used" in text
    assert res["download"]["downloaded_utc"] in text
    for bad in (FAKE, "SIGNED", STORAGE):
        assert bad not in text
    out = capsys.readouterr()
    assert FAKE not in out.out + out.err
    # a hand-written section at the end survives a rerun, which reads the cache and makes no request
    res["report"].write_text(text + "\n" + k.HAND_SECTION + "\n\nWritten by hand.\n")
    monkeypatch.setattr(HTTPAdapter, "send", lambda self, request, **kw: pytest.fail("network on a cached rerun"))
    again = k.run_h3(db_path=db, reports_dir=tmp_path / "rep")["report"].read_text()
    assert again.endswith("Written by hand.\n") and again.count(k.HAND_SECTION) == 1
