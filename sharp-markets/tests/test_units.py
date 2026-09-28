from datetime import date, datetime, timedelta, timezone

import pytest

from markets.build.match import OddsEvent, match_games
from markets.devig import blend, devig_proportional
from markets.kalshi.ingest import CHUNK_PERIODS, candle_windows
from markets.research.nfl_weather import interp_p_at, interp_strike_at, pava_decreasing, split_tail

UTC = timezone.utc


def test_devig_and_blend():
    fair = devig_proportional({"A": 1.8, "B": 2.1})
    assert fair["A"] + fair["B"] == pytest.approx(1)
    assert fair["A"] == pytest.approx((1 / 1.8) / (1 / 1.8 + 1 / 2.1))
    assert devig_proportional({"A": 1.0, "B": 2.0}) is None
    v, std, used = blend({"pinnacle": 0.6, "betonlineag": 0.5}, {"pinnacle": 0.55, "lowvig": 0.30, "betonlineag": 0.15})
    assert used == ["betonlineag", "pinnacle"]
    assert v == pytest.approx((0.6 * 0.55 + 0.5 * 0.15) / 0.70)
    assert std > 0


def test_candle_windows_under_cap_and_contiguous():
    start = 1_767_000_000 // 60 * 60
    end = start + 12_000 * 60
    w = candle_windows(start, end, 1)
    assert w[0][0] == start and w[-1][1] == end
    for (s1, e1), (s2, _) in zip(w, w[1:]):
        assert s2 == e1 + 1
    assert all((e - s) // 60 + 1 <= CHUNK_PERIODS for s, e in w)


def test_match_games_nearest_swapped_one_to_one():
    t0 = datetime(2026, 1, 6, 0, 30, tzinfo=UTC)
    ev = lambda i, h, a, dt: OddsEvent(i, h, a, dt, dt, dt)
    events = [ev("e1", "TOR", "ATL", t0 + timedelta(minutes=10)),      # correct game
              ev("e2", "ATL", "TOR", t0 + timedelta(hours=40)),       # same pair, outside window
              ev("e3", "NYK", "BKN", t0 - timedelta(minutes=5))]      # neutral site: home/away swapped
    games = [("g1", "ATL", "TOR", t0), ("g2", "NYK", "BKN", t0), ("g3", "LAL", "BOS", t0)]
    m, conflicts = match_games(games, events)
    assert m["g1"].odds_event_id == "e1" and m["g1"].tip_diff_min == 10 and not m["g1"].home_away_swapped
    assert m["g2"].home_away_swapped
    assert "g3" not in m and not conflicts
    # two Kalshi games competing for one odds event: nearest wins, the other is a conflict
    m, conflicts = match_games([("a", "ATL", "TOR", t0), ("b", "ATL", "TOR", t0 + timedelta(hours=3))], events[:1])
    assert m["a"].odds_event_id == "e1" and [c[0] for c in conflicts] == ["b"]


def test_ladder_helpers():
    assert pava_decreasing([0.9, 0.7, 0.75, 0.3]) == pytest.approx([0.9, 0.725, 0.725, 0.3])
    strikes, ps = [40.5, 43.5, 46.5], [0.7, 0.55, 0.35]
    assert interp_strike_at(strikes, ps) == pytest.approx(43.5 + 0.05 / 0.20 * 3)
    assert interp_strike_at(strikes, [0.9, 0.8, 0.7]) is None                  # not bracketed
    assert interp_p_at(strikes, ps, 45.0) == pytest.approx(0.45)
    assert split_tail("NYGNE", {"NYG", "NE", "NYJ"}) == ("NYG", "NE")
    assert split_tail("LACLE", {"LAC", "LA", "CLE"}) == ("LA", "CLE") or split_tail("LACLE", {"LAC", "LA", "CLE"}) is None
