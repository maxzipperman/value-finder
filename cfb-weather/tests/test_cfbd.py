"""CFBD client: Bearer auth, cache-first, the call budget, and the parsers. No network."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cfbweather import cfbd  # noqa: E402

LINES = [{"id": 401, "season": 2024, "seasonType": "regular", "week": 3, "startDate": "2024-09-14T19:30:00.000Z",
          "homeTeam": "Iowa", "awayTeam": "Troy", "homeScore": 38, "awayScore": 21,
          "lines": [{"provider": "DraftKings", "spread": -21.5, "spreadOpen": -20.5, "overUnder": 45.5,
                     "overUnderOpen": 44.0, "homeMoneyline": -2000, "awayMoneyline": 1100},
                    {"provider": "ESPN Bet", "spread": -21.0, "spreadOpen": None, "overUnder": 45.0,
                     "overUnderOpen": None, "homeMoneyline": None, "awayMoneyline": None}]}]
TEAMS = [{"id": 401, "teams": [{"teamId": 1, "team": "Iowa", "conference": "Big Ten", "homeAway": "home", "points": 38,
                                "stats": [{"category": "totalYards", "stat": "412"}, {"category": "turnovers", "stat": "1"}]},
                               {"teamId": 2, "team": "Troy", "conference": "Sun Belt", "homeAway": "away", "points": 21,
                                "stats": [{"category": "totalYards", "stat": "301"}]}]}]
PLAYERS = [{"id": 401, "teams": [{"team": "Iowa", "conference": "Big Ten", "homeAway": "home", "points": 38, "categories": [
    {"name": "passing", "types": [{"name": "YDS", "athletes": [{"id": "9", "name": "QB One", "stat": "211"}]}]},
    {"name": "defensive", "types": [{"name": "TOT", "athletes": [{"id": "7", "name": "LB", "stat": "9"}]}]}]}]}]


class Resp:
    def __init__(self, body, status=200):
        self._body, self.status_code, self.ok, self.text = body, status, status < 400, json.dumps(body)

    def json(self):
        return self._body


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("CFBD_API_KEY", "k")
    monkeypatch.setattr(cfbd, "CACHE", tmp_path / "cfbd")
    seen = []

    def use(resp):
        def get(url, params=None, timeout=None, headers=None):
            seen.append((url, params, headers))
            return resp
        monkeypatch.setattr(cfbd.session, "get", get)
        return seen
    return use


def test_get_is_bearer_authed_and_cached(api):
    seen = api(Resp(LINES))
    assert cfbd.get("/lines", dict(year=2024, seasonType="regular")) == LINES
    assert cfbd.get("/lines", dict(year=2024, seasonType="regular")) == LINES     # second read: cache
    assert len(seen) == 1 and seen[0][2]["Authorization"] == "Bearer k"


@pytest.mark.parametrize("status", [401, 429, 500])
def test_errors_stop_cleanly(api, status):
    api(Resp({}, status))
    with pytest.raises(SystemExit):
        cfbd.get("/talent", dict(year=2024))


def test_budget_and_dry_run(api):
    seen = api(Resp([]))
    total, todo = cfbd.plan([2024])
    assert total == len(todo) == 2 + 2 + 17                       # lines x2, returning, talent, 17 weeks
    assert cfbd.pull([2024], confirm=False) == 0 and seen == []  # plan only
    with pytest.raises(SystemExit):
        cfbd.pull([2024], max_calls=5, confirm=True)
    assert cfbd.pull([2024], confirm=True, sleep=0) == 21 and len(seen) == 21
    assert cfbd.plan([2024])[1] == []                            # everything cached now


def test_parsers():
    ln = cfbd.lines_table([LINES])
    assert len(ln) == 2 and ln.iloc[0].total_open == 44.0 and ln.iloc[1].provider == "ESPN Bet"
    tb = cfbd.team_box_table([TEAMS])
    assert list(tb.team) == ["Iowa", "Troy"] and tb.iloc[0].totalYards == "412"
    pb = cfbd.player_box_table([PLAYERS])
    assert len(pb) == 1 and pb.iloc[0].category == "passing"      # defensive dropped
