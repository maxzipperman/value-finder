"""Load per-market minute series and sharp-line series from DuckDB into plain Python structures."""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass
class MarketSeries:
    market_ticker: str
    game_id: str
    team_code: str
    is_home: bool
    split: str
    commence: datetime
    result: int | None
    fee_multiplier: Decimal
    b2b: bool | None
    opp_b2b: bool | None
    ts: list[datetime] = field(default_factory=list)
    bid: list[Decimal | None] = field(default_factory=list)
    ask: list[Decimal | None] = field(default_factory=list)
    mid: list[float | None] = field(default_factory=list)
    ask_open_raw: list[Decimal | None] = field(default_factory=list)
    pin: list[float | None] = field(default_factory=list)
    blend: list[float | None] = field(default_factory=list)
    mtt: list[float] = field(default_factory=list)                 # minutes to tip
    yes_taker: dict[datetime, Decimal] = field(default_factory=dict)
    close_fair: dict[str, float | None] = field(default_factory=dict)  # {'pinnacle': .., 'blend': ..}

    def index_at_or_after(self, t: datetime) -> int | None:
        i = bisect.bisect_left(self.ts, t)
        return i if i < len(self.ts) else None

    def index_asof(self, t: datetime) -> int | None:
        i = bisect.bisect_right(self.ts, t) - 1
        return i if i >= 0 else None


@dataclass
class SharpSeries:
    """Pinnacle fair prob per snapshot for one (odds event, team)."""
    ts: list[datetime]
    pin: list[float]
    last_update: list[datetime | None]

    def asof(self, t: datetime) -> int | None:
        i = bisect.bisect_right(self.ts, t) - 1
        return i if i >= 0 else None


def load_markets(con, start: date, end: date, *, max_spread: float) -> dict[str, MarketSeries]:
    rows = con.execute("""
        SELECT a.market_ticker, a.game_id, a.team_code, a.is_home, a.split, a.commence_time, a.result, a.fee_multiplier,
               a.b2b, a.opp_b2b, a.ts, a.yes_bid, a.yes_ask, a.spread, a.yes_ask_open_raw, a.pin_fair, a.blend_fair,
               a.minutes_to_tip
        FROM analysis_1m a WHERE a.game_date_et BETWEEN ? AND ?
        ORDER BY a.market_ticker, a.ts""", [start, end]).fetchall()
    out: dict[str, MarketSeries] = {}
    for (mt, gid, team, is_home, split, commence, result, mult, b2b, opp_b2b, ts, bid, ask, spread, ask_open,
         pin, blend, mtt) in rows:
        ms = out.get(mt)
        if ms is None:
            ms = out[mt] = MarketSeries(mt, gid, team, is_home, split, commence, result, mult, b2b, opp_b2b)
        ms.ts.append(ts)
        ms.bid.append(bid)
        ms.ask.append(ask)
        ms.mid.append(float(bid + ask) / 2 if bid is not None and ask is not None and spread <= max_spread else None)
        ms.ask_open_raw.append(ask_open)
        ms.pin.append(pin)
        ms.blend.append(blend)
        ms.mtt.append(mtt)
    for mt, minute, vol in con.execute("""
            SELECT t.market_ticker, t.minute_end_ts, t.yes_taker_volume FROM kalshi_yes_taker_1m t
            JOIN (SELECT DISTINCT market_ticker FROM analysis_1m WHERE game_date_et BETWEEN ? AND ?) m USING (market_ticker)""",
                                       [start, end]).fetchall():
        if mt in out:
            out[mt].yes_taker[minute] = vol
    # closing fair = last sharp snapshot at or before commence
    for mt, pin_close, blend_close in con.execute("""
            SELECT m.market_ticker, f.pin_fair, f.blend_fair
            FROM (SELECT DISTINCT a.market_ticker, g.odds_event_id, a.team_code, g.commence_time
                  FROM analysis_1m a JOIN games g USING (sport, game_id) WHERE a.game_date_et BETWEEN ? AND ?) m
            ASOF LEFT JOIN sharp_fair f
              ON m.odds_event_id = f.odds_event_id AND m.team_code = f.team_code AND m.commence_time >= f.snapshot_ts""",
                                                  [start, end]).fetchall():
        if mt in out:
            out[mt].close_fair = {"pinnacle": pin_close, "blend": blend_close}
    return out


def load_sharp(con, start: date, end: date) -> dict[tuple[str, str], SharpSeries]:
    """{(game_id, team_code): SharpSeries} for pre-commence Pinnacle snapshots."""
    rows = con.execute("""
        SELECT g.game_id, f.team_code, f.snapshot_ts, f.pin_fair, f.pin_last_update
        FROM sharp_fair f JOIN games g ON f.odds_event_id = g.odds_event_id
        WHERE g.match_status = 'matched' AND g.game_date_et BETWEEN ? AND ? AND f.pin_fair IS NOT NULL
          AND f.snapshot_ts < g.commence_time
        ORDER BY 1, 2, 3""", [start, end]).fetchall()
    out: dict[tuple[str, str], SharpSeries] = {}
    for gid, team, ts, pin, lu in rows:
        s = out.setdefault((gid, team), SharpSeries([], [], []))
        s.ts.append(ts)
        s.pin.append(pin)
        s.last_update.append(lu)
    return out
