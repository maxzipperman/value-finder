"""H3 for the NFL (issue #75) on a small file built by hand, all offline.

The synthetic all_odds.csv follows the NBA file's layout. A synthetic nfl-weather folder holds the repo's two tables
the test reads: games.parquet (schedule and scores) and mos_replay.parquet (Rule B's wind trigger). Every number of the
6 variants is checked against arithmetic written out here. No network: HTTPAdapter.send fails the test.
"""
import csv
import io
import zipfile
from datetime import date, timedelta

import numpy as np
import pytest
from requests.adapters import HTTPAdapter
from scipy import stats

from markets.research import kaggle_h3 as k
from markets.research import kaggle_h3_nfl as n


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for name in ("KAGGLE_API_TOKEN", "KAGGLE_USERNAME", "KAGGLE_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(k, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(HTTPAdapter, "send", lambda self, request, **kw: pytest.fail("network call"))


# ---------------------------------------------------------------- the hand-built data

# The repo's schedule: game id, season, type, Eastern date, home, away, home score, away score (None: no score).
SCHEDULE = [
    ("2021_01_CLE_KC", 2021, "REG", "2021-09-12", "KC", "CLE", 33, 29),
    ("2021_01_BAL_LV", 2021, "REG", "2021-09-13", "LV", "BAL", 33, 27),
    ("2021_06_KC_WAS", 2021, "REG", "2021-10-17", "WAS", "KC", 13, 31),
    ("2022_01_JAX_WAS", 2022, "REG", "2022-09-11", "WAS", "JAX", 28, 22),
    ("2022_13_HOU_DEN", 2022, "REG", "2022-12-04", "DEN", "HOU", 10, 9),
    ("2022_17_BUF_CIN", 2022, "REG", "2023-01-02", "CIN", "BUF", None, None),     # the cancelled game
    ("2023_01_NE_PHI", 2023, "REG", "2023-09-10", "PHI", "NE", 25, 20),
    ("2023_04_KC_NYJ", 2023, "REG", "2023-10-01", "NYJ", "KC", 20, 23),
    ("2023_11_CLE_PIT", 2023, "REG", "2023-11-19", "PIT", "CLE", 10, 13),
    ("2024_03_CAR_ATL", 2024, "REG", "2024-09-22", "ATL", "CAR", 22, 36),
    ("2024_07_DET_MIN", 2024, "REG", "2024-10-20", "MIN", "DET", 29, 31),
    ("2024_10_TEN_LAC", 2024, "REG", "2024-11-10", "LAC", "TEN", 27, 17),
    ("2024_18_CHI_GB", 2024, "REG", "2025-01-05", "GB", "CHI", 24, 22),
    ("2025_01_BAL_BUF", 2025, "REG", "2025-09-07", "BUF", "BAL", 41, 40),
    ("2025_01_LA_SEA", 2025, "REG", "2025-09-07", "SEA", "LA", 38, 37),
    ("2025_18_SEA_SF", 2025, "REG", "2026-01-04", "SF", "SEA", 3, 13),
    ("2026_01_LAC_KC", 2026, "REG", "2026-09-13", "KC", "LAC", 99, 0),          # the 2026 season: never read
]

# One row of the file per entry: key, file date, home name, away name,
#   spread (home price, away price, home money share, home ticket share, home line),
#   total (over price, under price, over money share, over ticket share, line),
#   flags: None = the won flags the repo's scores give; or {market: (flag side 1, flag side 2)} to override.
# Side 2's shares are 100 minus side 1's; the away line is minus the home line and the under line the over line.
ROWS = [
    ("N1", "2021-09-12", "Kansas City Chiefs", "Cleveland Browns", (1.91, 1.91, 70, 55, -6.5), (1.87, 1.95, 40, 60, 54.5), None),
    ("N2", "2021-09-14", "Las Vegas Raiders", "Baltimore Ravens", (2.0, 1.8, 20, 25, 4.5), (1.91, 1.91, 50, 50, 50.5), None),
    ("N3", "2022-09-11", "Washington Commanders", "Jacksonville Jaguars", (1.91, 1.91, 45, 60, -3), (1.91, 1.91, 80, 65, 44), {"total": ("False", "True")}),
    ("N4", "2021-10-17", "Washington Football Team", "Kansas City", (1.95, 1.87, 50, 20, 6.5), (1.91, 1.91, 30, 20, 55.5), None),
    ("N5", "2023-09-10", "Philadelphia Eagles", "New England Patriots", (1.91, 1.91, 80, 60, -5), (1.91, 1.91, 35, 25, 45.5), None),
    ("N6", "2023-10-01", "NY Jets", "Kansas City Chiefs", (1.91, 1.91, 35, 15, 9.5), (1.91, 1.91, 60, 72, 42.5), {"spread": ("", "")}),
    ("N7", "2024-11-10", "Tennessee Titans", "L.A. Chargers", (2.0, 1.83, 40, 28, 8.5), (1.91, 1.91, 55, 55, 38.5), None),
    ("N8", "2025-01-05", "Green Bay Packers", "Chicago Bears", (1.91, 1.91, 50, 50, -10), (1.8, 2.05, 90, 75, 40.5), None),
    ("N9", "2025-09-07", "Buffalo Bills", "Baltimore Ravens", (1.91, 1.91, 30, 45, -1.5), (1.91, 1.91, 70, 80, 50.5), None),
    ("N10", "2025-09-07", "Seattle Seahawks", "Los Angeles Rams", (1.91, 1.91, 65, 40, 1.5), (1.91, 1.91, 20, 30, 41.5), None),
    ("N11", "2026-01-04", "San Francisco 49ers", "Seattle Seahawks", (1.91, 1.91, 55, 40, -1.5), (1.91, 1.91, 50, 50, 47.5), None),
    ("X1", "2026-09-13", "Kansas City Chiefs", "Los Angeles Chargers", (1.91, 1.91, 777, 777, -3.5), (1.91, 1.91, 777, 777, 47.5), None),
    ("X3", "2022-10-02", "New York", "Dallas Cowboys", (1.91, 1.91, 50, 50, -3.5), (1.91, 1.91, 50, 50, 44.5), None),
    ("X4", "2022-11-06", "Miami Dolphins", "Detroit Lions", (1.91, 1.91, 50, 50, -3.5), (1.91, 1.91, 50, 50, 44.5), None),
    ("X5", "2022-12-04", "Denver Broncos", "Houston Texans", (1.91, 1.91, 60, 50, -2.5), (1.91, 1.91, 50, 50, 36.5), None),
    ("X5", "2022-12-04", "Denver Broncos", "Houston Texans", (1.91, 1.91, 61, 50, -2.5), (1.91, 1.91, 50, 50, 36.5), None),
    ("X6", "2023-01-02", "Cincinnati Bengals", "Buffalo Bills", (1.91, 1.91, 50, 50, 1.5), (1.91, 1.91, 50, 45, 49.5), None),
    ("X7", "2023-11-19", "Pittsburgh Steelers", "Cleveland Browns", (1.91, 1.91, None, 50, 1.5), (1.91, 1.91, 50, 50, 33.5), None),
    ("X8", "2024-09-22", "Atlanta Falcons", "Carolina Panthers", (1.91, 1.91, 50, 50, -3.5), (1.5, 1.5, 50, 50, 40.5), None),
    ("X9", "2024-10-20", "Minnesota Vikings", "Detroit Lions", ((1.91, 1.91, 50, 50, -1.5), 2.5), (1.91, 1.91, 50, 50, 47.5), None),
]
DUPLICATE = "N1"                                   # written twice, identical in every column

# Rule B's wind trigger in the repo's replay table: game id, season, mos_signal.
TRIGGERS = [("2021_06_KC_WAS", 2021, True), ("2025_01_BAL_BUF", 2025, True), ("2021_01_CLE_KC", 2021, False),
            ("2021_07_NOT_INFILE", 2021, True), ("2026_01_LAC_KC", 2026, True)]

SCORES = {(g[4], g[5], g[3]): (g[6], g[7]) for g in SCHEDULE}


def _ours(home_pts, away_pts, market, line):
    """Side 1 / side 2 / push at the line, from the scores (written out again here, independently of the module)."""
    x = home_pts + line - away_pts if market == "spread" else home_pts + away_pts - line
    return "push" if x == 0 else (1 if x > 0 else 2)


def _csv_text(rows=ROWS, drop=(), duplicate=True):
    cols = ["", "game_id", "game_date", "away_team", "home_team", "pregame_odds"]
    for m, sides in (("total", ("over", "under")), ("money", ("away", "home")), ("spread", ("away", "home"))):
        for s in sides:
            cols += [f"{m}_{s}_{f}" for f in ("points", "stake_percentage", "wager_percentage", "odds",
                                              "decimal_odds", "won")]
    cols = [c for c in cols if c not in drop]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    sched = {g[0]: g for g in SCHEDULE}
    out = []
    for key, d, home, away, sp, tt, flags in rows:
        row = {"game_id": key, "game_date": f"{d}-10:00", "home_team": home, "away_team": away}
        mirror_off = 0.0
        if isinstance(sp[0], tuple):                                # X9: the away line doesn't mirror
            sp, mirror_off = sp[0], sp[1] - (-sp[0][4])
        for m, (p1, p2, st1, wg1, line), (s1, s2) in (("spread", sp, ("home", "away")),
                                                      ("total", tt, ("over", "under"))):
            l1, l2 = (line, -line + mirror_off) if m == "spread" else (line, line)
            won = ("", "")
            game = next((g for g in sched.values() if {g[4], g[5]} == {n.team_code(home), n.team_code(away)}
                         and g[6] is not None and abs((date.fromisoformat(g[3]) - date.fromisoformat(d)).days) <= 1),
                        None)
            if game is not None:
                hp, ap = (game[6], game[7]) if game[4] == n.team_code(home) else (game[7], game[6])
                r = _ours(hp, ap, m, line)
                won = {1: ("True", "False"), 2: ("False", "True"), "push": ("False", "False")}[r]
            if flags and m in flags:
                won = flags[m]
            for s, p, st, wg, ln, wn in ((s1, p1, st1, wg1, l1, won[0]),
                                         (s2, p2, None if st1 is None else 100 - st1, 100 - wg1, l2, won[1])):
                row |= {f"{m}_{s}_decimal_odds": p, f"{m}_{s}_stake_percentage": "" if st is None else st,
                        f"{m}_{s}_wager_percentage": wg, f"{m}_{s}_won": wn, f"{m}_{s}_points": ln}
        out.append(row)
        if duplicate and key == DUPLICATE:
            out.append(dict(row))
    for i, row in enumerate(out):                    # the unnamed row index: a running row number, as pandas writes it
        row[""] = str(i)
    w.writerows(out)
    return buf.getvalue()


def _zip(text, name="all_odds.csv"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(name, text)
    return buf.getvalue()


def _closing_lines(g):
    """nflverse's closing spread_line (the schedule's home side's expected margin) and total_line for a schedule game,
    made to agree with the file's rows: spread_line is minus the file's home line when the file's home side is the
    schedule's, plus it when the two are swapped."""
    for _, d, home, away, sp, tt, _ in ROWS:
        if {n.team_code(home), n.team_code(away)} == {g[4], g[5]} and \
                abs((date.fromisoformat(g[3]) - date.fromisoformat(d)).days) <= 1:
            line = sp[0][4] if isinstance(sp[0], tuple) else sp[4]
            return (-line if n.team_code(home) == g[4] else line), tt[4]
    return None, None


def _nfl_dir(tmp_path, schedule=SCHEDULE, triggers=TRIGGERS):
    import duckdb
    d = tmp_path / "nfl-weather"
    (d / "data" / "processed").mkdir(parents=True)
    con = duckdb.connect()
    con.execute("CREATE TABLE g (game_id VARCHAR, season BIGINT, game_type VARCHAR, gameday VARCHAR, "
                "home_team VARCHAR, away_team VARCHAR, home_score DOUBLE, away_score DOUBLE, spread_line DOUBLE, "
                "total_line DOUBLE)")
    con.executemany("INSERT INTO g VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [tuple(g) + _closing_lines(g) for g in schedule])
    con.execute(f"COPY g TO '{d / 'data' / 'processed' / 'games.parquet'}' (FORMAT PARQUET)")
    con.execute("CREATE TABLE t (game_id VARCHAR, season BIGINT, mos_signal BOOLEAN, under_win BOOLEAN)")
    con.executemany("INSERT INTO t VALUES (?, ?, ?, TRUE)", triggers)
    con.execute(f"COPY t TO '{d / 'data' / 'processed' / 'mos_replay.parquet'}' (FORMAT PARQUET)")
    con.close()
    return d


@pytest.fixture
def nfl_dir(tmp_path):
    return _nfl_dir(tmp_path)


def _run(nfl_dir, tmp_path, **kw):
    return n.run_h3_nfl(blob=_zip(_csv_text(**kw)), nfl_dir=nfl_dir, reports_dir=tmp_path / "rep")


def _v(res, family, market):
    return next(v for v in res["variants"] if v["family"] == family and v["market"] == market)


def _fair(a, b):
    return (1 / a) / (1 / a + 1 / b)


def _expected(bets):
    """Families A and C by hand: bets are (won, fair, price, Eastern date, season)."""
    r = np.array([w - f for w, f, _, _, _ in bets], float)
    m, nb = r.mean(), len(r)
    se_plain = r.std(ddof=1) / np.sqrt(nb)
    by = {}
    for (_, _, _, d, _), x in zip(bets, r):
        by[d] = by.get(d, 0.0) + (x - m)
    G = len(by)
    se_grouped = np.sqrt(G / (G - 1) * sum(v ** 2 for v in by.values()) / nb ** 2)
    se, df = (se_plain, nb - 1) if se_plain > se_grouped else (se_grouped, G - 1)
    z = stats.norm.isf(0.05 / 294 / 2)
    seasons = {}
    for (w, f, _, _, s), x in zip(bets, r):
        seasons.setdefault(s, []).append(x)
    return {"n": nb, "est": m, "se_plain": se_plain, "se_grouped": se_grouped, "G": G, "se": se,
            "p": 2 * stats.t.sf(abs(m) / se, df), "win_rate": np.mean([b[0] for b in bets]),
            "mean_fair": np.mean([b[1] for b in bets]),
            "roi": np.mean([(p - 1) if w else -1 for w, _, p, _, _ in bets]), "detectable": z * 0.5 / np.sqrt(nb),
            "season": {s: (float(np.mean(v)), len(v)) for s, v in seasons.items()}}


def _check(v, want):
    for key in ("n", "est", "se_plain", "se_grouped", "G", "se", "p", "win_rate", "mean_fair", "roi", "detectable"):
        assert v[key] == pytest.approx(want[key], rel=1e-9, abs=1e-12), key
    for s in n.SEASONS:
        got, nn = v["season"][s]
        if s in want["season"]:
            assert got == pytest.approx(want["season"][s][0]) and nn == want["season"][s][1], s
        else:
            assert got is None and nn == 0, s


# ---------------------------------------------------------------- the registration

def test_registration_constants_and_file():
    assert n.N_VARIANTS == 6 and n.PRIOR_COUNT == 288 and n.RUNNING_COUNT == 294
    assert n.BAR == pytest.approx(0.05 / 294) and f"{n.BAR:.6f}" == "0.000170"
    assert n.Z_BAR == pytest.approx(3.7598, abs=1e-4)
    assert n.MARKETS == ("spread", "total") and n.THRESHOLD == 10 and n.FADE_MAX_TICKETS == 30
    assert n.SEASONS == ("2021", "2022", "2023", "2024", "2025") and n.SEASONS_NEEDED == 4
    assert n.DATASET == "caseydurfee/mgm-grand-nfl-betting-data" and k.DATASETS["nba"] == k.DATASET
    reg = (k.Path(k.__file__).resolve().parents[3] / n.REGISTRATION_DOC).read_text()
    for phrase in ("6 variants", "288 to 294", "0.05 / 294 = **0.000170**", "said 287 to 293",
                   "at least 4 of the 5 seasons", "10 points", "30% of the tickets or fewer", "no moneylines",
                   "games.parquet", "push", "duplicate", "mos_replay.parquet", "column mapping",
                   "a null is the expected result", "round(money share − ticket share, 9) >= 10",
                   "round(ticket share, 9) <= 30", "Unnamed: 0", "two-team city name", "config/odds5m.yaml",
                   "13 of them are playoff games", "about 9 to 13 points", "about 720", "sha256",
                   "`REGISTRATION`", "no won flag", "the sign and mapping of the spread and total lines",
                   "The full run is not made until the check-only output has been read and any dated note made",
                   "then the game is counted under that unknown name"):
        assert phrase in reg, phrase
    assert "7 to 10 points of win chance" not in reg                  # the sentence the table contradicted


def test_the_nba_test_is_unchanged_by_the_sport_argument():
    assert k.N_VARIANTS == 14 and k.PRIOR_COUNT == 273 and k.RUNNING_COUNT == 287
    assert k._raw_base() == k.RAW_DIR / "nba" / "kaggle_mgm" and k._raw_base("nfl") == k.RAW_DIR / "nfl" / "kaggle_mgm"
    with pytest.raises(SystemExit):
        k.run("nhl")


# ---------------------------------------------------------------- team names

@pytest.mark.parametrize("name, code", [
    ("Washington Football Team", "WAS"), ("Washington Commanders", "WAS"), ("Washington", "WAS"),
    ("L.A. Rams", "LA"), ("LA Rams", "LA"), ("Los Angeles Rams", "LA"), ("LA Chargers", "LAC"),
    ("NY Giants", "NYG"), ("N.Y. Jets", "NYJ"), ("new  york jets", "NYJ"), ("Las Vegas Raiders", "LV"),
    ("Jacksonville Jaguars", "JAX"), ("San Francisco 49ers", "SF"), ("Kansas City", "KC"),
    ("New York", None), ("Los Angeles", None), ("NY", None), ("L.A.", None), ("Oakland Raiders", None),
    ("St. Louis Rams", None), ("", None),
])
def test_team_mapping(name, code):
    assert n.team_code(name) == code


def test_every_mapped_code_is_an_nflverse_code_in_the_repos_table():
    import duckdb
    path = k.Path(k.__file__).resolve().parents[4] / "nfl-weather" / "data" / "processed" / "games.parquet"
    if not path.is_file():
        pytest.skip("the repo's games.parquet is not in this checkout")
    codes = {r[0] for r in duckdb.sql(f"SELECT DISTINCT home_team FROM read_parquet('{path}') "
                                      "WHERE season BETWEEN 2021 AND 2025").fetchall()}
    assert set(n.TEAM_NAMES.values()) == codes


# ---------------------------------------------------------------- the three declarations and the join

def test_rows_duplicates_2026_and_the_join(nfl_dir, monkeypatch):
    seen = []
    real = k._num
    monkeypatch.setattr(k, "_num", lambda v: seen.append(str(v)) or real(v))
    rows, fields = n.load_rows(_zip(_csv_text()))
    n.check_columns(fields)
    sched = n.load_schedule(nfl_dir)
    assert {g["season"] for g in sched} == {2021, 2022, 2023, 2024, 2025}          # no 2026 row is read
    assert "home_score" not in sched[0]                                              # and no score, here
    games, info = n.prepare(rows, sched)
    assert info["n_rows"] == len(ROWS) + 1
    assert info["exact_duplicate_rows"] == 1               # N1 twice, with different row numbers: dropped to one
    assert info["index_columns"] == [""]
    assert info["later_seasons"] == {2026: 1} and info["earlier_seasons"] == {}
    assert info["unknown_teams"] == {}                     # X3's "New York": Dallas has no game, so it is left out
    assert info["city_names"] == {("New York", "left out"): 1}
    assert info["left_out"] == {"two-team city name not resolved": 1, "no game in the repo's schedule": 1,
                                "the same game on two rows that differ": 2}
    assert len(games) == 15 and [g["game_id"] for g in games].count("2021_01_CLE_KC") == 1
    assert "2026_01_LAC_KC" not in {g["game_id"] for g in games}
    assert info["swapped"] == 1 and info["date_offsets"] == {0: 14, -1: 1}
    n2 = next(g for g in games if g["game_id"] == "2021_01_BAL_LV")
    assert n2["date"] == date(2021, 9, 13) and n2["file_date"] == date(2021, 9, 14)
    n11 = next(g for g in games if g["game_id"] == "2025_18_SEA_SF")
    assert n11["season"] == "2025"                                                    # January 2026: the 2025 season
    assert seen == []                                                                 # prepare reads no figure
    n.read_figures(games, info)
    assert "777" not in seen and "777.0" not in seen                                  # nor the 2026 row, ever
    assert info["share_scale"] == 1.0 and not info["american_prices"]


def test_results_come_from_the_scores_and_pushes_are_left_out(nfl_dir, tmp_path):
    res = _run(nfl_dir, tmp_path)
    assert res["n_variants"] == 6 and len(res["variants"]) == 6
    assert res["n_joined"] == 15 and res["n_games"] == 14
    assert res["info"]["left_out"]["no final score in the repo's table"] == 1         # the cancelled game
    assert res["excluded"]["spread"] == {"missing figure": 1, n.MIRROR: 1, "push": 1}  # X7, X9, N5
    assert res["excluded"]["total"] == {"margin below 0% or above 20%": 1}            # X8
    assert res["n_records"] == {"spread": 11, "total": 13}
    # the swapped game: the file's home side (Tennessee, +8.5) lost 17 + 8.5 - 27; its record is Tennessee's
    games = res["checks"]
    assert games["per_season"]["2024"]["games"] == 4 and games["per_season"]["2022"]["scored"] == 1


def test_the_won_flags_are_only_a_cross_check(nfl_dir, tmp_path):
    res = _run(nfl_dir, tmp_path)
    fl = res["flags"]
    assert fl["spread"]["counts"] == {"agree": 12, n.BLANK_FLAG: 1}                   # N6 blank; N5's push agrees
    assert fl["total"]["counts"] == {"agree": 13, "disagree": 1}                       # N3: the file says under
    assert fl["total"]["pairs"] == {("under", "over"): 1}
    # N7, joined with home and away swapped, is also counted on its own: its flags follow the file's home side
    assert fl["spread"]["swapped"] == {"agree": 1} and fl["total"]["swapped"] == {"agree": 1}
    # the flag that disagrees changes nothing: N3's over still counts as a win in family A (below)
    a = _v(res, "A", "total")
    flipped = _run(nfl_dir, tmp_path, rows=[r if r[0] != "N3" else r[:6] + (None,) for r in ROWS])
    assert _v(flipped, "A", "total")["est"] == pytest.approx(a["est"])


def test_family_a_by_hand(nfl_dir, tmp_path):
    res = _run(nfl_dir, tmp_path)
    f4, f7 = _fair(1.95, 1.87), _fair(2.0, 1.83)
    # spread, money - tickets >= 10: N1 home (+15, lost), N3 away (+15, lost), N4 home (+30, lost), N6 home (+20, won),
    # N7 Tennessee (+12, lost), N9 away (+15, won), N10 home (+25, won), N11 home (+15, lost). N5 is a push.
    want = _expected([(0, .5, 1.91, "2021-09-12", "2021"), (0, .5, 1.91, "2022-09-11", "2022"),
                      (0, f4, 1.95, "2021-10-17", "2021"), (1, .5, 1.91, "2023-10-01", "2023"),
                      (0, f7, 2.0, "2024-11-10", "2024"), (1, .5, 1.91, "2025-09-07", "2025"),
                      (1, .5, 1.91, "2025-09-07", "2025"), (0, .5, 1.91, "2026-01-04", "2025")])
    v = _v(res, "A", "spread")
    _check(v, want)
    assert v["est"] == pytest.approx((-f4 - f7) / 8)                # the six even bets cancel: three won, three lost
    assert v["signs"] == {"2021": -1, "2022": -1, "2023": 1, "2024": -1, "2025": 1} and v["same_sign"] == 3
    assert not v["passes"] and v["both_sides"] == 0
    # total: N1 under (+20, lost), N3 over (+15, won), N4 over (+10, lost), N5 over (+10, lost), N6 under (+12, lost),
    # N8 over (+15, won), N9 under (+10, lost), N10 under (+10, lost)
    fu1, fo8 = _fair(1.95, 1.87), _fair(1.8, 2.05)
    want = _expected([(0, fu1, 1.95, "2021-09-12", "2021"), (1, .5, 1.91, "2022-09-11", "2022"),
                      (0, .5, 1.91, "2021-10-17", "2021"), (0, .5, 1.91, "2023-09-10", "2023"),
                      (0, .5, 1.91, "2023-10-01", "2023"), (1, fo8, 1.8, "2025-01-05", "2024"),
                      (0, .5, 1.91, "2025-09-07", "2025"), (0, .5, 1.91, "2025-09-07", "2025")])
    _check(_v(res, "A", "total"), want)


def test_family_c_by_hand(nfl_dir, tmp_path):
    res = _run(nfl_dir, tmp_path)
    f2, f4, f7 = _fair(2.0, 1.8), _fair(1.95, 1.87), _fair(2.0, 1.83)
    # spread, 30% of the tickets or fewer: N2 home (25%, won), N4 home (20%, lost), N6 home (15%, won),
    # N7 Tennessee (28%, lost). N2 is grouped on the schedule's date, September 13, not the file's 14th.
    v = _v(res, "C", "spread")
    _check(v, _expected([(1, f2, 2.0, "2021-09-13", "2021"), (0, f4, 1.95, "2021-10-17", "2021"),
                         (1, .5, 1.91, "2023-10-01", "2023"), (0, f7, 2.0, "2024-11-10", "2024")]))
    assert v["roi"] == pytest.approx((1.0 - 1 + 0.91 - 1) / 4)
    # total: N4 over (20%, lost), N5 over (25%, lost), N6 under (28%, lost), N8 under (25%, lost),
    # N9 under (20%, lost), N10 over (exactly 30%: "30% or fewer" includes it, won)
    fo8 = _fair(1.8, 2.05)
    v = _v(res, "C", "total")
    _check(v, _expected([(0, .5, 1.91, "2021-10-17", "2021"), (0, .5, 1.91, "2023-09-10", "2023"),
                         (0, .5, 1.91, "2023-10-01", "2023"), (0, 1 - fo8, 2.05, "2025-01-05", "2024"),
                         (0, .5, 1.91, "2025-09-07", "2025"), (1, .5, 1.91, "2025-09-07", "2025")]))
    assert v["signs"] == {"2021": -1, "2022": None, "2023": -1, "2024": -1, "2025": 0}
    assert v["same_sign"] == 3 and not v["passes"]


def test_family_b_matches_statsmodels(nfl_dir, tmp_path):
    import statsmodels.api as sm
    res = _run(nfl_dir, tmp_path)
    # the home side (the over) of every tested game: (won, fair, divergence, Eastern date, season)
    f2, f4, fo8 = _fair(2.0, 1.8), _fair(1.95, 1.87), _fair(1.8, 2.05)
    rows = {"spread": [(0, .5, 15, "2021-09-12"), (1, f2, -5, "2021-09-13"), (1, .5, -15, "2022-09-11"),
                       (0, f4, 30, "2021-10-17"), (1, .5, 20, "2023-10-01"), (0, _fair(2.0, 1.83), 12, "2024-11-10"),
                       (0, .5, 0, "2025-01-05"), (0, .5, -15, "2025-09-07"), (1, .5, 25, "2025-09-07"),
                       (0, .5, 15, "2026-01-04"), (0, .5, 0, "2024-09-22")],
            "total": [(1, _fair(1.87, 1.95), -20, "2021-09-12"), (1, .5, 0, "2021-09-13"), (1, .5, 15, "2022-09-11"),
                      (0, .5, 10, "2021-10-17"), (0, .5, 10, "2023-09-10"), (1, .5, -12, "2023-10-01"),
                      (1, .5, 0, "2024-11-10"), (1, fo8, 15, "2025-01-05"), (1, .5, -10, "2025-09-07"),
                      (1, .5, -10, "2025-09-07"), (0, .5, 0, "2026-01-04"), (0, .5, 0, "2023-11-19"),
                      (1, .5, 0, "2024-10-20")]}
    for m, rs in rows.items():
        y = np.array([w - f for w, f, _, _ in rs])
        x = np.array([dv / 10 for _, _, dv, _ in rs])
        tenth = np.array([min(int(f * 10), 9) for _, f, _, _ in rs])
        present = sorted(set(tenth))
        X = np.column_stack([np.ones(len(y)), x] + [(tenth == q).astype(float) for q in present[1:]])
        groups = np.array([date.fromisoformat(d).toordinal() for *_, d in rs])
        hc1 = sm.OLS(y, X).fit(cov_type="HC1")
        cl = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": groups})
        v = _v(res, "B", m)
        assert v["n"] == len(y) and v["est"] == pytest.approx(hc1.params[1])
        assert v["se_plain"] == pytest.approx(hc1.bse[1]) and v["se_grouped"] == pytest.approx(cl.bse[1])
        wider = max(hc1.bse[1], cl.bse[1])
        df = len(y) - X.shape[1] if hc1.bse[1] > cl.bse[1] else len(set(groups)) - 1
        assert v["p"] == pytest.approx(2 * stats.t.sf(abs(v["est"]) / wider, df))
        assert v["detectable"] == pytest.approx(stats.norm.isf(0.05 / 294 / 2) * 0.5 / (np.sqrt(len(y)) * x.std(ddof=1)))
        assert set(v["season"]) == set(n.SEASONS)
        # the season figures, fitted on each season alone, by hand
        by_season = {}
        for w, f, dv, d in rs:
            by_season.setdefault(str(n.season_of(date.fromisoformat(d))), []).append((w, f, dv))
        for season in n.SEASONS:
            got, nn = v["season"][season]
            assert nn == len(by_season.get(season, []))
            want = _season_coef(by_season.get(season, []))
            assert (got is None) == (want is None), (m, season)
            if want is not None:
                assert got == pytest.approx(want, abs=1e-9), (m, season)
    # in this small file only 2025's spreads (three games, all at even money) and a few totals seasons can be fitted
    assert _v(res, "B", "spread")["season"]["2025"][0] is not None
    assert _v(res, "B", "spread")["season"]["2021"][0] is None


def _season_coef(rows):
    """Family B on one season, by hand: OLS of (won - fair) on [1, divergence / 10, fair-chance tenth dummies]; None
    when there are no more games than coefficients or the divergence doesn't vary (as the registration's NBA code)."""
    if not rows:
        return None
    y = np.array([w - f for w, f, _ in rows], float)
    x = np.array([dv / 10 for _, _, dv in rows], float)
    tenth = np.array([min(int(f * 10), 9) for _, f, _ in rows])
    present = sorted(set(tenth.tolist()))
    X = np.column_stack([np.ones(len(y)), x] + [(tenth == q).astype(float) for q in present[1:]])
    if len(y) <= X.shape[1] or np.ptp(x) == 0:
        return None
    return float(np.linalg.lstsq(X, y, rcond=None)[0][1])


def _synthetic_games():
    """Five seasons of eight games each, built in code: in 2021-24 the home side covers (the over wins) exactly when
    its share of money beats its share of tickets, and in 2025 the other way round, so family B's figure should have
    the same sign in 4 of the 5 seasons."""
    prices = [(1.91, 1.91), (1.8, 2.05), (2.05, 1.8), (1.5, 2.7), (2.7, 1.5)]
    divs = [-20, -10, -5, 5, 10, 15, 20, -15]
    games = []
    for si, season in enumerate(n.SEASONS):
        for j in range(8):
            a, b = prices[(si + j) % len(prices)]
            dv, dt = divs[(j + si) % 8], divs[(j + 2 * si + 3) % 8]
            flip = season == "2025"
            cover, over = (dv > 0) != flip, (dt > 0) != flip
            if j == 5:                                          # one exception a season, so no fit is perfect
                cover, over = not cover, not over
            games.append({"date": date(int(season), 10, 1 + j), "season": season, "game_id": f"{season}_{j}",
                          "home_pts": 27.0 if cover else 20.0, "away_pts": 20.0 if cover else 27.0,
                          "m": {"spread": {"home": {"dec": a, "stake": 50 + dv / 2, "wager": 50 - dv / 2, "line": -2.5},
                                           "away": {"dec": b, "stake": 50 - dv / 2, "wager": 50 + dv / 2, "line": 2.5}},
                                "total": {"over": {"dec": b, "stake": 50 + dt / 2, "wager": 50 - dt / 2,
                                                   "line": 44.5 if over else 50.5},
                                          "under": {"dec": a, "stake": 50 - dt / 2, "wager": 50 + dt / 2,
                                                    "line": 44.5 if over else 50.5}}}})
    return games


def test_family_b_season_figures_and_the_sign_check_by_hand():
    games = _synthetic_games()
    res = n.analyse(games)
    for m, s1 in (("spread", "home"), ("total", "over")):
        v = _v(res, "B", m)
        figures = {}
        for season in n.SEASONS:
            rows = []
            for g in games:
                if g["season"] != season:
                    continue
                a, b = g["m"][m][s1], g["m"][m][n.SIDES[m][1]]
                fair = _fair(a["dec"], b["dec"])
                won = (g["home_pts"] + a["line"] - g["away_pts"] > 0) if m == "spread" \
                    else (g["home_pts"] + g["away_pts"] - a["line"] > 0)
                rows.append((int(won), fair, a["stake"] - a["wager"]))
            figures[season] = _season_coef(rows)
            assert v["season"][season][0] == pytest.approx(figures[season], abs=1e-9) and v["season"][season][1] == 8
        overall = np.sign(v["est"])
        signs = {s: (0 if abs(f) < 1e-12 else int(np.sign(f))) for s, f in figures.items()}
        same = sum(1 for f in signs.values() if f == overall)
        assert v["signs"] == signs and v["same_sign"] == same
        assert overall == 1 and signs["2025"] == -1 and same == 4           # 4 of 5: the sign check is met
        assert v["passes"] == (v["p"] < 0.05 / 294 and same >= 4)


def test_the_sign_check_and_the_bar_of_294():
    """4 of 5 seasons with the same sign is enough, 3 is not; p must be below 0.05 / 294, which is stricter than the
    brief's 0.05 / 293."""
    four = {"2021": (0.1, 9), "2022": (0.2, 9), "2023": (-0.1, 9), "2024": (0.3, 9), "2025": (0.1, 9)}
    three = four | {"2025": (None, 0)}
    zero = four | {"2025": (1e-17, 9)}
    p_between = (0.05 / 294 + 0.05 / 293) / 2
    ok = k._sign_check({"est": 0.1, "p": 0.0001, "season": four}, bar=n.BAR)
    assert ok["same_sign"] == 4 and ok["passes"]
    assert not k._sign_check({"est": 0.1, "p": 0.0001, "season": three}, bar=n.BAR)["passes"]
    assert not k._sign_check({"est": 0.1, "p": 0.0001, "season": zero}, bar=n.BAR)["passes"]  # zero is no sign
    assert k._sign_check({"est": 0.1, "p": p_between, "season": four}, bar=0.05 / 293)["passes"]
    assert not k._sign_check({"est": 0.1, "p": p_between, "season": four}, bar=n.BAR)["passes"]


def test_both_sides_qualifying_is_left_out_and_counted(nfl_dir, tmp_path):
    """Shares that don't add up can put both sides over a rule: the game leaves that variant and is counted."""
    text = _csv_text().splitlines()
    head = text[0].split(",")
    rows = list(csv.DictReader(io.StringIO("\n".join(text))))
    for r in rows:
        if r["home_team"] == "Green Bay Packers":          # N8: home 50/50 on the spread; make both sides +10
            r |= {"spread_home_stake_percentage": "60", "spread_home_wager_percentage": "50",
                  "spread_away_stake_percentage": "60", "spread_away_wager_percentage": "50"}
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=head)
    w.writeheader()
    w.writerows(rows)
    res = n.run_h3_nfl(blob=_zip(buf.getvalue()), nfl_dir=nfl_dir, reports_dir=tmp_path / "rep")
    assert _v(res, "A", "spread")["both_sides"] == 1 and _v(res, "A", "spread")["n"] == 8


# ---------------------------------------------------------------- the Rule B description

def test_rule_b_description_is_counts_only(nfl_dir, tmp_path):
    res = _run(nfl_dir, tmp_path)
    rb = res["rule_b"]
    assert rb["n_triggers"] == 3 and rb["in_file"] == 2                  # the 2026 trigger is not read
    assert rb["by_season"] == {"2021": 2, "2025": 1}
    assert dict(rb["bins"]["trigger"]) == {20: 1, 80: 1}                 # N4 (20% on the over), N9 (80%)
    assert dict(rb["bins"]["all"]) == {20: 2, 30: 1, 40: 1, 50: 6, 60: 2, 70: 2, 80: 1}
    assert sum(rb["bins"]["all"].values()) + rb["no_share"]["all"] == res["n_joined"]
    assert set(rb) == {"n_triggers", "by_season", "in_file", "bins", "no_share"}    # nothing about results


def test_rule_b_reads_no_result_column(nfl_dir):
    import duckdb
    trig = n.load_rule_b_triggers(nfl_dir)
    assert trig == {"2021_06_KC_WAS": "2021", "2025_01_BAL_BUF": "2025", "2021_07_NOT_INFILE": "2021"}
    # the replay table's under_win column is there in the synthetic file, and the query never names it
    cols = [r[0] for r in duckdb.sql(f"DESCRIBE SELECT * FROM '{nfl_dir}/data/processed/mos_replay.parquet'").fetchall()]
    assert "under_win" in cols
    import inspect
    assert "under_win" not in inspect.getsource(n.load_rule_b_triggers)


# ---------------------------------------------------------------- a file that differs

def test_missing_columns_stop_the_run_and_name_them(nfl_dir, tmp_path):
    drop = ("spread_home_stake_percentage", "total_under_points")
    with pytest.raises(SystemExit) as e:
        n.run_h3_nfl(blob=_zip(_csv_text(drop=drop)), nfl_dir=nfl_dir, reports_dir=tmp_path / "rep")
    text = str(e.value)
    assert "2 expected columns are missing" in text and all(c in text for c in drop)
    assert "column mapping" in text and "Nothing was computed" in text
    assert not (tmp_path / "rep").exists()


def test_a_zip_without_all_odds_stops(nfl_dir, tmp_path):
    with pytest.raises(SystemExit) as e:
        n.run_h3_nfl(blob=_zip(_csv_text(), name="other.csv"), nfl_dir=nfl_dir, reports_dir=tmp_path / "rep")
    assert "all_odds.csv" in str(e.value)


def test_check_only_reads_no_score_or_won_flag(nfl_dir, tmp_path, monkeypatch):
    real = n.load_schedule

    def schedule(nfl_dir, with_scores=False):
        assert not with_scores, "check-only loaded the scores"
        return real(nfl_dir, with_scores)

    monkeypatch.setattr(n, "load_schedule", schedule)
    monkeypatch.setattr(n, "attach_scores", lambda *a: pytest.fail("check-only attached the scores"))
    monkeypatch.setattr(n, "won_flag_check", lambda *a: pytest.fail("check-only compared the won flags"))
    monkeypatch.setattr(n, "outcome", lambda *a: pytest.fail("check-only computed a result"))
    monkeypatch.setattr(k, "_b", lambda v: pytest.fail("check-only read a won flag"))
    seen = []
    real_num = k._num
    monkeypatch.setattr(k, "_num", lambda v: seen.append(str(v)) or real_num(v))
    res = n.run_h3_nfl(blob=_zip(_csv_text()), nfl_dir=nfl_dir, reports_dir=tmp_path / "rep", check_only=True)
    assert res["report"] is None and not (tmp_path / "rep").exists()
    # prices, shares and lines were read for the format counts; no won flag went through a number reader
    won = {r[f"{m}_{s}_won"] for r in csv.DictReader(io.StringIO(_csv_text())) for m, ss in n.SIDES.items()
           for s in ss} - {""}
    assert seen and not (set(seen) & won)
    assert "777" not in seen and "777.0" not in seen                            # nor the 2026 row
    text = "\n".join(res["check"])
    assert "New York -> left out: 1" in text and "{2026: 1}" in text and "joined to the repo's schedule: 15 games" in text
    assert "Rule B trigger games 2021-25 in the repo's table: 3; in the file: 2" in text
    assert "shares read as percentages; prices read as decimal odds" in text
    fmt = res["format"]
    assert fmt["spread"]["counts"][n.MIRROR] == 1                               # X9
    assert fmt["spread"]["counts"]["missing splits"] == 1                       # X7
    assert fmt["total"]["counts"][n.MARGIN] == 1                                # X8: 1.5 and 1.5, a margin of 33%
    assert fmt["spread"]["counts"]["whole-number line"] == 3                    # N3 (-3), N5 (-5), N8 (-10)
    assert fmt["total"]["counts"]["whole-number line"] == 1                     # N3 (44)
    assert fmt["spread"]["counts"]["missing line"] == 0 and fmt["spread"]["counts"]["unreadable line"] == 0
    assert fmt["spread"]["wager_sum_within_1"] == 1.0 and fmt["spread"]["stake_sum_within_1"] == 1.0
    assert "spreads (15 joined games)" in text and f"{n.MIRROR} 1" in text
    assert "games.parquet " + n._sha256_file(nfl_dir / "data" / "processed" / "games.parquet") in text


def test_check_only_counts_missing_and_unreadable_lines_and_american_fractional_figures(nfl_dir, tmp_path):
    rows = list(csv.DictReader(io.StringIO(_csv_text())))
    for r in rows:
        for c in list(r):
            if c.endswith("_percentage") and r[c] not in ("", None):
                r[c] = repr(float(r[c]) / 100)                                # shares as fractions
            if c.endswith("_decimal_odds") and r[c] not in ("", None):
                x = float(r[c])                                               # prices as American odds
                r[c] = str(round((x - 1) * 100)) if x >= 2 else str(round(-100 / (x - 1)))
        if r["home_team"] == "Philadelphia Eagles":
            r["spread_home_points"] = "n/a"                                   # N5: an unreadable line
        if r["home_team"] == "Buffalo Bills":
            r["total_over_points"] = r["total_under_points"] = ""             # N9: a missing line
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
    res = n.run_h3_nfl(blob=_zip(buf.getvalue()), nfl_dir=nfl_dir, reports_dir=tmp_path / "rep", check_only=True)
    assert res["info"]["share_scale"] == 100.0 and res["info"]["american_prices"]
    assert res["format"]["spread"]["counts"]["unreadable line"] == 1
    assert res["format"]["total"]["counts"]["missing line"] == 1
    assert "shares read as fractions (multiplied by 100); prices read as American odds" in "\n".join(res["check"])


# ---------------------------------------------------------------- the report and the command

def test_report(nfl_dir, tmp_path):
    res = _run(nfl_dir, tmp_path)
    path = res["report"]
    assert path.name == "h3_kaggle_nfl.md"
    text = path.read_text()
    assert "n_variants_tested = 6" in text and "288 to 294" in text and "0.000170" in text
    assert "None of the 6 variants passes the bar" in text and "recorded as a null" in text
    assert "Rule B trigger games" in text and "| 20% to under 30% | 1 | 2 |" in text
    assert "\"New York\" → left out (1)" in text and "2026: 1" in text and "Unnamed row index" in text
    assert "1 disagree" in text and res["sha256"] in text
    assert "of which on games joined with home and away swapped: 1 agree" in text
    for name in ("games.parquet", "mos_replay.parquet"):
        h = n._sha256_file(nfl_dir / "data" / "processed" / name)
        assert res["inputs"][name] == h and f"`{name}` `{h}`" in text
    assert res["registration"] is None or res["registration"]["commit"] in text
    for v in res["variants"]:
        assert n._name(v) in text
    # a hand-written section survives a rerun
    path.write_text(text + "\n" + n.HAND_SECTION + "\n\nWritten by hand.\n")
    again = _run(nfl_dir, tmp_path)["report"].read_text()
    assert again.endswith("Written by hand.\n") and again.count(n.HAND_SECTION) == 1


def test_command_line_reads_the_cache_and_picks_the_sport(nfl_dir, tmp_path, monkeypatch, capsys):
    from markets import cli
    cache = k.RAW_DIR / "nfl" / "kaggle_mgm" / "2026-09-30"
    cache.mkdir(parents=True)
    (cache / "dataset.zip").write_bytes(_zip(_csv_text()))
    cli.main(["h3-kaggle", "--sport", "nfl", "--check-only", "--nfl-dir", str(nfl_dir)])
    out = capsys.readouterr().out
    assert "check only" in out and "joined to the repo's schedule: 15 games" in out
    monkeypatch.setattr(n, "REPORTS_DIR", tmp_path / "rep")
    cli.main(["--sport", "nfl", "h3-kaggle", "--nfl-dir", str(nfl_dir)])
    assert "n_variants_tested=6" in capsys.readouterr().out
    assert (tmp_path / "rep" / "h3_kaggle_nfl.md").exists()
    called = []
    monkeypatch.setattr(k, "run_h3", lambda **kw: called.append(kw) or {
        "n_rows": 0, "n_games": 0, "unknown_teams": {}, "kalshi_joined_games": 0, "n_variants": 14, "report": "x"})
    cli.main(["h3-kaggle"])
    assert called == [{}]                                        # the NBA test, as before, with no argument
    with pytest.raises(SystemExit):                              # --check-only is for the NFL test only
        cli.main(["h3-kaggle", "--check-only"])
    with pytest.raises(SystemExit):                              # two different sports
        cli.main(["--sport", "nfl", "h3-kaggle", "--sport", "nba"])
    assert called == [{}]


# ---------------------------------------------------------------- review fixes: thresholds, names, rows, flags, record

def _edit(text, edits):
    """The CSV with some cells changed: edits = {home team name: {column: value}}."""
    rows = list(csv.DictReader(io.StringIO(text)))
    for r in rows:
        r |= edits.get(r["home_team"], {})
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def _fractions(text):
    rows = list(csv.DictReader(io.StringIO(text)))
    for r in rows:
        for c in r:
            if c.endswith("_percentage") and r[c] not in ("", None):
                r[c] = repr(round(float(r[c]) / 100, 6))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def test_share_thresholds_are_rounded_to_nine_decimals():
    assert 16.4 - 6.4 < 10 and n.money_ahead({"div": 16.4 - 6.4})              # 9.999999999999998 is 10
    a, b = 0.57 * 100, 0.47 * 100
    assert a - b < 10 and n.money_ahead({"div": a - b})                        # fractions, scaled to percent
    assert not n.money_ahead({"div": 10 - 1e-8})                               # a real shortfall still counts
    assert n.few_tickets({"wager": 30.000000000000004}) and n.few_tickets({"wager": 30 + 1e-10})
    assert not n.few_tickets({"wager": 30 + 1e-8})
    assert n._bin(70 - 1e-14) == 70 and n._bin(69.99) == 60 and n._bin(100.0) == 90


def test_family_a_at_16_4_and_6_4_and_at_0_57_and_0_47(nfl_dir, tmp_path):
    base = _v(_run(nfl_dir, tmp_path), "A", "spread")
    # N8 (Green Bay at home, 50/50 on the spread, won nothing on the spread: 24 - 10 - 22 < 0): the home side gets
    # 16.4% of the money and 6.4% of the tickets, 10 points ahead once rounded
    pct = _edit(_csv_text(), {"Green Bay Packers": {
        "spread_home_stake_percentage": "16.4", "spread_home_wager_percentage": "6.4",
        "spread_away_stake_percentage": "83.6", "spread_away_wager_percentage": "93.6"}})
    v = _v(n.run_h3_nfl(blob=_zip(pct), nfl_dir=nfl_dir, reports_dir=tmp_path / "rep"), "A", "spread")
    assert v["n"] == base["n"] + 1
    assert v["est"] == pytest.approx((base["est"] * base["n"] + (0 - 0.5)) / (base["n"] + 1))
    # the same file with every share as a fraction, and N8 at 0.57 and 0.47: the same bets, the same figures
    frac = _edit(_fractions(_csv_text()), {"Green Bay Packers": {
        "spread_home_stake_percentage": "0.57", "spread_home_wager_percentage": "0.47",
        "spread_away_stake_percentage": "0.43", "spread_away_wager_percentage": "0.53"}})
    res = n.run_h3_nfl(blob=_zip(frac), nfl_dir=nfl_dir, reports_dir=tmp_path / "rep")
    assert res["info"]["share_scale"] == 100.0
    assert _v(res, "A", "spread")["n"] == base["n"] + 1
    full = _run(nfl_dir, tmp_path)
    for fam in ("A", "C"):                                  # every other variant: identical to the percent file
        assert _v(res, fam, "total")["n"] == _v(full, fam, "total")["n"]
        assert _v(res, fam, "total")["est"] == pytest.approx(_v(full, fam, "total")["est"])
    assert _v(res, "C", "spread")["n"] == _v(full, "C", "spread")["n"]


def _sched(*games):
    return [{"game_id": gid, "season": int(d[:4]), "game_type": "REG", "gameday": date.fromisoformat(d),
             "home_team": h, "away_team": a} for gid, d, h, a in games]


def _rows(*rows, extra=None):
    return [{"game_date": f"{d}-13:00", "home_team": h, "away_team": a, **(extra or {})} for d, h, a in rows]


def test_two_team_city_names_resolve_from_the_schedule_alone():
    sched = _sched(("g1", "2022-10-02", "NYG", "DAL"), ("g2", "2022-10-09", "LAC", "NYJ"),
                   ("g3", "2023-10-01", "DEN", "LA"), ("g4", "2023-10-02", "DEN", "LAC"),
                   ("g5", "2024-10-06", "NYJ", "NYG"))
    rows = _rows(("2022-10-02", "New York", "Dallas Cowboys"),       # only the Giants play Dallas: NYG
                 ("2022-10-08", "Los Angeles", "NY"),                 # both names two-team: left out
                 ("2022-10-10", "L.A.", "New York Jets"),             # only the Chargers play the Jets: LAC
                 ("2023-10-01", "Denver Broncos", "Los Angeles"),     # both LA teams play Denver within a day: out
                 ("2023-10-01", "Dallas Cowboys", "New York"),        # the Giants play Dallas, a year earlier: out
                 ("2024-10-06", "New York", "New York"))              # Jets against Giants: left out
    games, info = n.prepare(rows, sched)
    assert [(g["game_id"], g["home"], g["away"]) for g in games] == [("g1", "NYG", "DAL"), ("g2", "LAC", "NYJ")]
    assert info["left_out"] == {"two-team city name not resolved": 4}
    assert info["unknown_teams"] == {}
    assert info["city_names"] == {("New York", "NYG"): 1, ("L.A.", "LAC"): 1, ("Los Angeles", "left out"): 2,
                                  ("NY", "left out"): 1, ("New York", "left out"): 3}
    # a city name against a name the mapping lacks: the unknown name is counted, never guessed
    games, info = n.prepare(_rows(("2022-10-02", "New York", "Big D")), sched)
    assert games == [] and info["unknown_teams"] == {"Big D": 1}
    assert info["left_out"] == {"team name not in the mapping": 1}


def test_the_duplicate_check_ignores_an_unnamed_row_index():
    sched = _sched(("g1", "2022-10-02", "NYG", "DAL"), ("g2", "2022-10-09", "MIA", "BUF"))
    for col in ("", "Unnamed: 0"):
        rows = [r | {col: str(i)} for i, r in enumerate(_rows(("2022-10-02", "NY Giants", "Dallas"),
                                                               ("2022-10-02", "NY Giants", "Dallas"),
                                                               ("2022-10-09", "Miami", "Buffalo"),
                                                               ("2022-10-09", "Miami", "Buffalo")))]
        rows[3]["total_over_points"] = "44.5"                  # differs in a real column: not a duplicate
        games, info = n.prepare(rows, sched)
        assert info["index_columns"] == [col] and info["exact_duplicate_rows"] == 1
        assert [g["game_id"] for g in games] == ["g1"]
        assert info["left_out"] == {"the same game on two rows that differ": 2}
    assert n.is_row_index("") and n.is_row_index("Unnamed: 0") and n.is_row_index(" ")
    assert not n.is_row_index("game_id") and not n.is_row_index("Unnamed")


def test_flags_on_swapped_games_are_counted_on_their_own(nfl_dir, tmp_path):
    # N7: the file names Tennessee at home; the schedule has the Chargers at home. A flag written for the schedule's
    # home side (the Chargers covered 27 - 8.5 - 17) says the file's home side won the spread: a disagreement, and it
    # shows among the swapped games
    text = _edit(_csv_text(), {"Tennessee Titans": {"spread_home_won": "True", "spread_away_won": "False"}})
    res = n.run_h3_nfl(blob=_zip(text), nfl_dir=nfl_dir, reports_dir=tmp_path / "rep")
    fl = res["flags"]["spread"]
    assert fl["counts"] == {"agree": 11, "disagree": 1, n.BLANK_FLAG: 1}
    assert fl["swapped"] == {"disagree": 1} and fl["pairs"] == {("home", "away"): 1}
    assert _v(res, "A", "spread")["est"] == pytest.approx(_v(_run(nfl_dir, tmp_path), "A", "spread")["est"])


def test_the_2026_cut_is_the_sealed_window_in_odds5m():
    import yaml
    cfg = yaml.safe_load((k.Path(k.__file__).resolve().parents[3] / "config" / "odds5m.yaml").read_text())
    win = next(w for w in cfg["sports"]["americanfootball_nfl"]["windows"] if w["label"] == "2026")
    assert win["sealed"] is True and n.SEALED_FROM <= date.fromisoformat(str(win["from"]))
    assert n.season_of(n.SEALED_FROM) == n.LAST_SEASON + 1
    assert n.season_of(n.SEALED_FROM - timedelta(days=1)) == n.LAST_SEASON


def test_the_registration_is_read_from_git_until_the_hub_pins_it(nfl_dir, tmp_path, monkeypatch):
    assert n.REGISTRATION == {"commit": None, "committed_utc": None, "github_utc": None}   # never guessed
    res = _run(nfl_dir, tmp_path)
    if res["registration"] is not None:
        assert not res["registration"]["pinned"] and "the hub pins it" in res["report"].read_text()
    monkeypatch.setattr(n, "REGISTRATION", {"commit": "c" * 40, "committed_utc": "2026-09-30T01:00:00Z",
                                            "github_utc": "2026-09-30T01:00:05Z"})
    text = _run(nfl_dir, tmp_path)["report"].read_text()
    assert f"commit `{'c' * 40}`, committed 2026-09-30T01:00:00Z; on GitHub at 2026-09-30T01:00:05Z" in text


def _transform(text, fn):
    rows = list(csv.DictReader(io.StringIO(text)))
    for r in rows:
        fn(r)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def _flip_spread(r):
    for s in ("home", "away"):
        c = f"spread_{s}_points"
        if r[c] not in ("", None):
            r[c] = repr(-float(r[c]))


def _moneylines(r):
    """Moneyline prices that agree with the file's own spread: the side giving points is the favourite."""
    fav_home = float(r["spread_home_points"]) < 0
    r["money_home_decimal_odds"], r["money_away_decimal_odds"] = ("1.6", "2.4") if fav_home else ("2.4", "1.6")


def _check_only(nfl_dir, tmp_path, text):
    return n.run_h3_nfl(blob=_zip(text), nfl_dir=nfl_dir, reports_dir=tmp_path / "rep", check_only=True)


def test_check_only_checks_the_sign_and_mapping_of_the_lines(nfl_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(k, "_b", lambda v: pytest.fail("the line checks read a won flag"))
    monkeypatch.setattr(n, "attach_scores", lambda *a: pytest.fail("the line checks read a score"))
    good = _check_only(nfl_dir, tmp_path, _transform(_csv_text(), _moneylines))
    lc = good["format"]["lines"]
    assert lc["spread"] == {"same sign": 15, "opposite sign": 0, "a line of zero": 0, "missing": 0,
                            "within 3 points": 15}                    # N7, swapped, compared with +spread_line
    assert lc["total"] == {"within 3 points": 15, "more than 3 points apart": 0, "missing": 0}
    assert lc["moneyline"] == {"agree": 15, "disagree": 0, "no favourite or a line of zero": 0, "missing": 0}
    # both spread lines negated: nothing else in the check changes, and the line checks show it
    bad = _check_only(nfl_dir, tmp_path, _transform(_transform(_csv_text(), _moneylines), _flip_spread))
    lc = bad["format"]["lines"]
    assert lc["spread"]["opposite sign"] == 15 and lc["spread"]["same sign"] == 0
    assert lc["spread"]["within 3 points"] == 6                          # the lines of 1.5 points or less
    assert lc["moneyline"]["disagree"] == 15 and lc["moneyline"]["agree"] == 0
    text = "\n".join(bad["check"])
    assert "opposite sign 15" in text and "disagree 15" in text
    assert "\n".join(good["check"]) != text
    # a total read from the wrong column shows too
    off = _check_only(nfl_dir, tmp_path, _transform(_csv_text(), lambda r: r.update(
        total_over_points=str(float(r["total_over_points"]) + 10), total_under_points=str(
            float(r["total_under_points"]) + 10))))
    assert off["format"]["lines"]["total"]["more than 3 points apart"] == 15


def test_line_checks_without_moneylines_or_nflverse_lines(nfl_dir, tmp_path):
    res = _check_only(nfl_dir, tmp_path, _csv_text(drop=("money_home_decimal_odds",)))
    assert res["format"]["lines"]["moneyline"] is None
    assert "no moneyline prices in the file" in "\n".join(res["check"])
    res = _check_only(nfl_dir, tmp_path, _csv_text())                  # the columns are there, but blank
    assert res["format"]["lines"]["moneyline"]["missing"] == 15


def test_the_report_shows_the_line_checks_and_says_they_are_the_check_only_code(nfl_dir, tmp_path):
    text = _run(nfl_dir, tmp_path)["report"].read_text()
    assert "spread lines against nflverse's closing spread_line" in text and "same sign 15" in text
    assert "come from the same code as the check-only output" in text


def test_the_order_note_uses_the_github_time_once_pinned():
    dl = {"downloaded_utc": "2026-10-01T12:00:00Z"}
    git_only = {"commit": "c", "committed": "2026-09-30T01:00:00+00:00", "github": None}
    assert "commit time is before the download (the commit time, not the time it reached GitHub)" in \
        n._order_note(git_only, dl)
    assert "on GitHub before the download" in n._order_note(git_only | {"github": "2026-09-30T01:00:05Z"}, dl)
    assert "reached GitHub after the download" in n._order_note(git_only | {"github": "2026-10-02T00:00:00Z"}, dl)
    assert n._order_note(git_only, {}) == ""
