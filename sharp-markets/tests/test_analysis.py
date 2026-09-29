from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import duckdb
import pytest

from markets.analysis.backtest import FillParams, pinnacle_moves, simulate_fill
from markets.analysis.data import MarketSeries, SharpSeries
from markets.build import sql

UTC = timezone.utc
TIP = datetime(2026, 1, 6, 0, 0, tzinfo=UTC)


def at(h, m, day=5):
    return datetime(2026, 1, day, h, m, tzinfo=UTC)


@pytest.fixture
def con():
    c = duckdb.connect()
    c.execute("SET TimeZone = 'UTC'")
    c.execute("""CREATE TABLE games AS SELECT 'nba' sport, 'G' game_id, 'AAA' away_code, 'BBB' home_code, 'E1' odds_event_id,
                 TIMESTAMPTZ '2026-01-06 00:00:00+00' commence_time, 'train' split, 1.0::DECIMAL(6,4) fee_multiplier,
                 DATE '2026-01-05' game_date_et, false home_b2b, true away_b2b, 'matched' match_status""")
    c.execute("""CREATE TABLE kalshi_markets AS SELECT * FROM (VALUES
                 ('nba', 'G-BBB', 'G', 'BBB', 'yes', TIMESTAMPTZ '2026-01-05 22:00:00+00'),
                 ('nba', 'G-AAA', 'G', 'AAA', 'no',  TIMESTAMPTZ '2026-01-05 22:00:00+00'))
                 t(sport, market_ticker, game_id, team_code, result, open_time)""")
    c.execute("CREATE TABLE excluded_markets (sport VARCHAR, market_ticker VARCHAR)")
    c.execute("""CREATE TABLE kalshi_candles AS SELECT 'nba' sport, 'G-BBB' market_ticker, CAST(ts AS TIMESTAMPTZ) end_ts,
                 CAST(b AS DECIMAL(6,4)) yes_bid_close, CAST(a AS DECIMAL(6,4)) yes_ask_close, CAST(ao AS DECIMAL(6,4)) yes_ask_open,
                 CAST(v AS DECIMAL(18,2)) volume FROM (VALUES
                 ('2026-01-05 22:01:00+00', 0.40, 0.42, 0.42, 10), ('2026-01-05 22:10:00+00', 0.41, 0.43, 0.42, 5),
                 ('2026-01-05 23:30:00+00', 0.45, 0.47, 0.46, 7)) t(ts, b, a, ao, v)""")
    c.execute("""CREATE TABLE sharp_fair AS SELECT 'nba' sport, CAST(ts AS TIMESTAMPTZ) snapshot_ts, 'E1' odds_event_id, 'BBB' team_code,
                 CAST(p AS DOUBLE) pin_fair, CAST(p AS DOUBLE) blend_fair, 0.0::DOUBLE blend_std, 'pinnacle' books_used, CAST(NULL AS TIMESTAMPTZ) pin_last_update FROM (VALUES
                 ('2026-01-05 22:00:00+00', 0.50), ('2026-01-05 22:30:00+00', 0.52), ('2026-01-05 23:55:00+00', 0.60)) t(ts, p)""")
    c.execute(sql.analysis_sql(fair_source="pinnacle", ffill_max_min=30, sharp_max_min=65, taker_rate=0.07))
    return c


def row(con, ts):
    cols = [d[0] for d in con.execute("SELECT * FROM analysis_1m LIMIT 0").description]
    r = con.execute("SELECT * FROM analysis_1m WHERE market_ticker = 'G-BBB' AND ts = ?", [ts]).fetchone()
    return dict(zip(cols, r))


def test_no_lookahead_anywhere(con):
    assert con.execute("SELECT count(*) FROM analysis_1m WHERE sharp_snapshot_ts > ts OR fill_age_min < 0").fetchone()[0] == 0
    assert row(con, at(22, 29))["pin_fair"] == pytest.approx(0.50)        # 22:30 snapshot not yet known
    assert row(con, at(22, 30))["pin_fair"] == pytest.approx(0.52)


def test_forward_fill_flags_volume_and_staleness(con):
    r = row(con, at(22, 5))
    assert r["is_filled"] and r["volume"] == 0 and r["yes_ask"] == D("0.42")
    r = row(con, at(22, 10))
    assert not r["is_filled"] and r["volume"] == 5 and r["yes_ask_open_raw"] == D("0.42")
    assert row(con, at(22, 40))["yes_ask"] == D("0.43")                   # 30 min old: still usable
    assert row(con, at(22, 41))["yes_ask"] is None                        # > 30 min: NULL
    assert row(con, at(23, 30))["yes_ask"] == D("0.47")


def test_sharp_staleness_edge_and_moves(con):
    assert row(con, at(23, 35))["pin_fair"] == pytest.approx(0.52)        # 65 min old
    assert row(con, at(23, 36))["pin_fair"] is None                       # 66 min old -> stale
    r = row(con, at(23, 56))
    assert r["pin_fair"] == pytest.approx(0.60)
    assert r["sharp_move_last_60min"] == pytest.approx(0.60 - 0.52)
    assert r["edge_vs_ask_net_of_fee"] == pytest.approx(0.60 - 0.47 - 0.07 * 0.47 * 0.53)
    assert r["minutes_to_tip"] == pytest.approx(4)
    assert r["b2b"] is False and r["opp_b2b"] is True and r["result"] == 1


def test_grid_bounds(con):
    lo, hi = con.execute("SELECT min(ts), max(ts) FROM analysis_1m").fetchone()
    assert lo == at(22, 1) and hi == TIP + timedelta(minutes=15)


def _series():
    ts = [TIP - timedelta(minutes=10 - k) for k in range(12)]      # tip-10m .. tip+1m
    ms = MarketSeries("M", "G", "BBB", True, "train", TIP, 1, D("1"), False, False)
    ms.ts = ts
    ms.ask = [D("0.50")] * len(ts)
    ms.bid = [D("0.48")] * len(ts)
    ms.mid = [0.49] * len(ts)
    ms.ask_open_raw = [None] * len(ts)
    ms.ask_open_raw[3] = D("0.52")                                   # ask jumped at the start of minute 3
    ms.pin = [0.60] * len(ts)
    ms.blend = ms.pin
    ms.mtt = [(TIP - t).total_seconds() / 60 for t in ts]
    ms.yes_taker = {t: D("40") for t in ts}
    ms.close_fair = {"pinnacle": 0.62}
    return ms


def test_fill_capped_by_participation_and_never_below_decision_ask():
    ms = _series()
    fp = FillParams(stake=D("100"), participation=D("0.25"), window=5, rounding="per_order")
    f = simulate_fill(ms, 2, "pinnacle", 0.01, fp)
    assert f["qty_req"] == 200
    assert f["n_fill_minutes"] == 5 and f["qty"] == 50                 # 10 per minute x 5 minutes
    assert f["cost"] == D("10") * D("0.52") + 40 * D("0.50")            # minute 3 filled at the higher open ask


def test_no_fill_after_tip():
    ms = _series()
    fp = FillParams(stake=D("100"), participation=D("1"), window=5, rounding="per_order")
    f = simulate_fill(ms, 8, "pinnacle", 0.01, fp)                    # tip-2m: only 1 pre-tip minute left
    assert f["n_fill_minutes"] == 1 and f["qty"] == 40


def test_the_close_is_strictly_before_tip_and_post_tip_rows_stay(con):
    """Audit 2 (Sep 29, 2026, Astra C5): the NBA close took the last sharp snapshot AT OR BEFORE the scheduled start,
    so a quote at the start itself (possibly in-play) became the close. Now it is strictly before, as load_sharp
    already was: 0.50 five minutes before tip, 0.99 at tip, the close is 0.50. Post-tip snapshots stay in
    sharp_fair and in analysis_1m's post-tip minutes, where the lead-lag analysis reads them."""
    from datetime import date

    from markets.analysis.data import load_markets
    con.execute("CREATE TABLE kalshi_yes_taker_1m (sport VARCHAR, market_ticker VARCHAR, minute_end_ts TIMESTAMPTZ, "
                "yes_taker_volume DECIMAL(18,2))")
    con.execute("DELETE FROM sharp_fair")
    con.execute("""INSERT INTO sharp_fair SELECT 'nba', CAST(ts AS TIMESTAMPTZ), 'E1', 'BBB', p, p, 0.0, 'pinnacle', NULL
                   FROM (VALUES ('2026-01-05 23:55:00+00', 0.50), ('2026-01-06 00:00:00+00', 0.99),
                                ('2026-01-06 00:05:00+00', 0.97)) t(ts, p)""")
    con.execute(sql.analysis_sql(fair_source="pinnacle", ffill_max_min=30, sharp_max_min=65, taker_rate=0.07))
    ms = load_markets(con, date(2026, 1, 5), date(2026, 1, 5), max_spread=1.0)["G-BBB"]
    assert ms.close_fair == {"pinnacle": pytest.approx(0.50), "blend": pytest.approx(0.50)}
    assert row(con, TIP + timedelta(minutes=5))["pin_fair"] == pytest.approx(0.97)     # post-tip, for lead-lag


def test_pinnacle_moves_need_dense_reference():
    s = SharpSeries([TIP - timedelta(minutes=m) for m in (120, 60, 10, 5)], [0.50, 0.50, 0.51, 0.55], [None] * 4)
    ev = pinnacle_moves(s, TIP, 0.03, 5)
    assert len(ev) == 1 and ev[0]["delta"] == pytest.approx(0.04)
    assert pinnacle_moves(s, TIP, 0.03, 30) == []                      # reference 60m away: not a 30-min move
